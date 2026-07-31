import re
with open("c:/Users/Admin/Documents/AI/Prediction Model/schedule_predict.py", "r", encoding="utf-8") as f:
    content = f.read()

data_func = '''
def predict_schedule_data(league="LPL", model_type="lr", db_path=DB_PATH, use_cache=True):
    # 1. Fetch schedule
    try:
        schedule_data = fetch_schedule(use_cache=use_cache, db_path=db_path)
    except Exception:
        return {"error": "Cannot retrieve schedule"}

    events = schedule_data.get("data", {}).get("schedule", {}).get("events", [])
    if not events:
        return {"predictions": [], "model_info": {"name": model_type, "training_rows": 0}, "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}

    bovada_events = fetch_bovada_odds()
    latest_stats, name_to_id = get_latest_team_stats(db_path, league_filter=league)

    model, scaler = None, None
    if model_type != "qwen_llm":
        try:
            model, scaler = train_model_for_league(league, model_type=model_type, db_path=db_path)
        except Exception as e:
            return {"error": f"Failed to train model for {league}: {e}"}

    now = datetime.datetime.now(datetime.timezone.utc)
    three_days_later = now + datetime.timedelta(days=3)

    predictions = []

    for ev in events:
        state = ev.get("state")
        start_time_str = ev.get("startTime", "")
        if not start_time_str:
            continue
        
        start_time = datetime.datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        if not (now - datetime.timedelta(hours=12) <= start_time <= three_days_later):
            continue

        league_name = ev.get("league", {}).get("name", "")
        if league.upper() not in league_name.upper():
            continue

        teams = ev.get("match", {}).get("teams", [])
        if len(teams) < 2:
            continue

        blue_api_name = teams[0].get("name", "Unknown")
        red_api_name = teams[1].get("name", "Unknown")

        is_actually_past = start_time < (now - datetime.timedelta(minutes=15))
        if state == "completed" and is_actually_past:
            try:
                from real_data_pipeline import crawl_completed_match
                match_date_str = start_time.strftime("%Y-%m-%d")
                crawl_completed_match(blue_api_name, red_api_name, match_date_str, db_path=db_path)
            except Exception as e:
                print(f"[AUTO-CRAWL] Warning: Failed to crawl completed match {blue_api_name} vs {red_api_name}: {e}")
            continue

        blue_db_name = normalize_name(blue_api_name)
        red_db_name = normalize_name(red_api_name)

        blue_feats, blue_fallback = get_team_features(blue_db_name, latest_stats, name_to_id)
        red_feats, red_fallback = get_team_features(red_db_name, latest_stats, name_to_id)

        if model_type == "qwen_llm":
            from llm_predict import predict_match_probability
            proba_blue = predict_match_probability(
                blue_name=blue_api_name, red_name=red_api_name,
                blue_elo=blue_feats["Elo"], red_elo=red_feats["Elo"],
                blue_obj=blue_feats["ObjCtrl"], red_obj=red_feats["ObjCtrl"],
                blue_kills=blue_feats["AvgKills"], red_kills=red_feats["AvgKills"],
                blue_dur=blue_feats["AvgDuration"], red_dur=red_feats["AvgDuration"],
                blue_drag=blue_feats["AvgDragons"], red_drag=red_feats["AvgDragons"],
                blue_towers=blue_feats["AvgTowers"], red_towers=red_feats["AvgTowers"],
                blue_gold=blue_feats["AvgGold"], red_gold=red_feats["AvgGold"]
            )
            proba = [1.0 - proba_blue, proba_blue]
            pred_class = 1 if proba_blue >= 0.5 else 0
            pred_winner = blue_api_name if pred_class == 1 else red_api_name
            winner_prob = proba_blue if pred_class == 1 else (1.0 - proba_blue)
        else:
            input_vector = np.array([[
                blue_feats["Elo"], red_feats["Elo"],
                blue_feats["ObjCtrl"], red_feats["ObjCtrl"],
                blue_feats["AvgKills"], red_feats["AvgKills"],
                blue_feats["AvgDuration"], red_feats["AvgDuration"],
                blue_feats["AvgDragons"], red_feats["AvgDragons"],
                blue_feats["AvgTowers"], red_feats["AvgTowers"],
                blue_feats["AvgGold"], red_feats["AvgGold"],
                0.50, 0.50
            ]])
            input_scaled = scaler.transform(input_vector)
            proba = model.predict_proba(input_scaled)[0]
            pred_class = model.predict(input_scaled)[0]
            pred_winner = blue_api_name if pred_class == 1 else red_api_name
            winner_prob = proba[1] if pred_class == 1 else proba[0]

        matched_bev = None
        direction = None
        b_team_a, b_team_b = None, None
        
        for bev in bovada_events:
            desc = bev.get("description", "")
            if " vs " not in desc:
                continue
            b_teams = desc.split(" vs ")
            b_team_a = b_teams[0].strip()
            b_team_b = b_teams[1].strip()
            
            direction = match_bovada_teams(b_team_a, b_team_b, blue_api_name, red_api_name)
            if direction:
                matched_bev = bev
                break

        best_of = 3
        market_probs = calculate_secondary_markets(proba[1], best_of=best_of)

        bovada_odds = None
        if matched_bev:
            bovada_odds = parse_bovada_markets_for_event(matched_bev, b_team_a, b_team_b)

        if not is_actually_past:
            state = "unstarted"

        if bovada_odds and state == "unstarted":
            match_date = start_time_str[:10]
            save_odds_to_db(
                blue_db_name or blue_api_name,
                red_db_name or red_api_name,
                match_date, bovada_odds, direction,
                (b_team_a, b_team_b) if matched_bev else None,
                db_path=db_path
            )

        time_local = datetime.datetime.fromisoformat(start_time_str.replace("Z", "+00:00")).astimezone()
        time_local_str = time_local.strftime("%Y-%m-%d %H:%M")

        kelly_dict = None
        if state == "unstarted":
            chosen_odds = 1.95
            if bovada_odds:
                blue_key = b_team_a if direction == "direct" else b_team_b
                red_key = b_team_b if direction == "direct" else b_team_a
                ml_blue = bovada_odds["ml"].get(blue_key)
                ml_red = bovada_odds["ml"].get(red_key)
                if ml_blue and ml_red:
                    chosen_odds = ml_blue if pred_winner == blue_api_name else ml_red
            
            kc = kelly_criterion(winner_prob, chosen_odds, bankroll=1000.0, fractional=0.5)
            kelly_dict = {
                "full_kelly_fraction": kc.full_kelly_fraction,
                "applied_fraction": kc.applied_fraction,
                "wager_pct": kc.wager_pct,
                "wager_amount": kc.wager_amount,
                "edge": kc.edge,
                "expected_value": kc.expected_value,
                "fractional_multiplier": kc.fractional_multiplier
            }

        predictions.append({
            "time": start_time_str,
            "time_local": time_local_str,
            "blue": blue_api_name,
            "red": red_api_name,
            "blue_db": blue_db_name,
            "red_db": red_db_name,
            "blue_fallback": blue_fallback,
            "red_fallback": red_fallback,
            "predicted_winner": pred_winner,
            "winner_prob": float(winner_prob),
            "blue_prob": float(proba[1]),
            "red_prob": float(proba[0]),
            "state": state,
            "bovada_odds": bovada_odds,
            "market_probs": market_probs,
            "kelly": kelly_dict,
            "best_of": best_of,
            "direction": direction,
            "bovada_names": (b_team_a, b_team_b) if matched_bev else None
        })

    return {
        "predictions": predictions,
        "model_info": {"name": model_type, "training_rows": 0},
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
'''

new_predict_schedule = '''
def predict_schedule(league="LPL", model_type="lr", db_path=DB_PATH, use_cache=True, show_markets=False):
    print("=" * 60)
    print(f"  PREDICTING UPCOMING {league} MATCHES (3 DAYS) WITH DYNAMIC BETTING LINES")
    print("=" * 60)
    
    data = predict_schedule_data(league, model_type, db_path, use_cache)
    if "error" in data:
        print(f"[ERROR] {data['error']}")
        return

    predictions = data.get("predictions", [])
    if not predictions:
        print(f"No upcoming/recent matches found for {league} in the 3-day window.")
        return

    print("\\n--- SCHEDULE, PREDICTIONS & BETTING LINES ---")
    for p in predictions:
        fallback_str = ""
        if p.get("blue_fallback") or p.get("red_fallback"):
            f_teams = []
            if p.get("blue_fallback"): f_teams.append(p["blue"])
            if p.get("red_fallback"): f_teams.append(p["red"])
            fallback_str = f" [Fallback defaults used for: {', '.join(f_teams)}]"

        print(f"\\nMatch: {p['time_local']} | {p['blue']} vs {p['red']} | Status: {p['state']}{fallback_str}")
        print(f"   Model Match Winner Probabilities:")
        print(f"     * P({p['blue']} Win): {p['blue_prob']:.2%}")
        print(f"     * P({p['red']} Win): {p['red_prob']:.2%}")
        
        ml_odds_info = "Not found on Bovada. Using fallback 1.95."
        chosen_odds = 1.95
        
        if p["bovada_odds"]:
            blue_key = p["bovada_names"][0] if p["direction"] == "direct" else p["bovada_names"][1]
            red_key = p["bovada_names"][1] if p["direction"] == "direct" else p["bovada_names"][0]
            ml_blue = p["bovada_odds"]["ml"].get(blue_key)
            ml_red = p["bovada_odds"]["ml"].get(red_key)
            if ml_blue and ml_red:
                ml_odds_info = f"{p['blue']}: {ml_blue:.2f} | {p['red']}: {ml_red:.2f}"
                chosen_odds = ml_blue if p["predicted_winner"] == p["blue"] else ml_red
                
        print(f"   Match Winner Odds : {ml_odds_info}")
        print(f"     * Predicted Winner: {p['predicted_winner']} ({p['winner_prob']:.2%})")

        if p["state"] == "unstarted":
            result = kelly_criterion(p["winner_prob"], chosen_odds, bankroll=1000.0, fractional=0.5)
            summary_clean = result.summary().replace("✅", "[OK]").replace("❌", "[SKIP]")
            print(f"     * Suggestion: {summary_clean}")

        if show_markets:
            print("\\n   --- DETAILED SECONDARY MARKETS ---")
            
            def show_kelly_for_market(label, prob, odds_val):
                if odds_val is None:
                    fair = 1.0 / prob if prob > 0 else float('inf')
                    print(f"     - {label:<15} : Prob = {prob:>6.2%} | Fair Odds = {fair:>5.2f} | Odds: N/A")
                    return
                fair = 1.0 / prob if prob > 0 else float('inf')
                edge_val = prob * odds_val - 1.0
                if edge_val > 0 and p["state"] == "unstarted":
                    kc = kelly_criterion(prob, odds_val, bankroll=1000.0, fractional=0.5)
                    bet_str = f"Bet {kc.wager_pct:.2f}% (${kc.wager_amount:.1f})"
                else:
                    bet_str = "No Edge"
                print(f"     - {label:<15} : Prob = {prob:>6.2%} | Fair Odds = {fair:>5.2f} | Live Odds = {odds_val:>5.2f} | {bet_str}")

            print("   1. Map Handicap (Point Spread):")
            hc_blue = None
            hc_red = None
            hc_blue_val = 1.5
            hc_red_val = -1.5
            
            if p["bovada_odds"]:
                blue_key = p["bovada_names"][0] if p["direction"] == "direct" else p["bovada_names"][1]
                red_key = p["bovada_names"][1] if p["direction"] == "direct" else p["bovada_names"][0]
                hc_blue_info = p["bovada_odds"]["handicap"].get(blue_key, {})
                hc_red_info = p["bovada_odds"]["handicap"].get(red_key, {})
                hc_blue = hc_blue_info.get("price")
                hc_blue_val = hc_blue_info.get("handicap", 1.5)
                hc_red = hc_red_info.get("price")
                hc_red_val = hc_red_info.get("handicap", -1.5)
                
            blue_hc_prob = p["market_probs"]["Blue +1.5"] if hc_blue_val == 1.5 else p["market_probs"]["Blue -1.5"]
            red_hc_prob = p["market_probs"]["Red +1.5"] if hc_red_val == 1.5 else p["market_probs"]["Red -1.5"]
            show_kelly_for_market(f"Blue {hc_blue_val:+.1f}", blue_hc_prob, hc_blue)
            show_kelly_for_market(f"Red {hc_red_val:+.1f}", red_hc_prob, hc_red)

            print("   2. Total Maps (Over/Under):")
            tot_over = None
            tot_under = None
            if p["bovada_odds"]:
                tot_over = p["bovada_odds"]["total"].get("Over", {}).get("price")
                tot_under = p["bovada_odds"]["total"].get("Under", {}).get("price")
            show_kelly_for_market("Over 2.5", p["market_probs"]["Over 2.5"], tot_over)
            show_kelly_for_market("Under 2.5", p["market_probs"]["Under 2.5"], tot_under)

            print("   3. Correct Scores:")
            cs_20 = None
            cs_21 = None
            cs_12 = None
            cs_02 = None
            if p["bovada_odds"]:
                blue_key = p["bovada_names"][0] if p["direction"] == "direct" else p["bovada_names"][1]
                red_key = p["bovada_names"][1] if p["direction"] == "direct" else p["bovada_names"][0]
                cs_20 = p["bovada_odds"]["correct_score"].get(f"{blue_key} 2-0")
                cs_21 = p["bovada_odds"]["correct_score"].get(f"{blue_key} 2-1")
                cs_12 = p["bovada_odds"]["correct_score"].get(f"{red_key} 2-1")
                cs_02 = p["bovada_odds"]["correct_score"].get(f"{red_key} 2-0")
                
                if not cs_20 or not cs_21 or not cs_12 or not cs_02:
                    ml_blue = p["bovada_odds"]["ml"].get(blue_key)
                    ml_red = p["bovada_odds"]["ml"].get(red_key)
                    if ml_blue and ml_red:
                        try:
                            ip_blue = 1.0 / ml_blue
                            ip_red = 1.0 / ml_red
                            margin = ip_blue + ip_red - 1.0
                            norm_blue = ip_blue / (ip_blue + ip_red)
                            p_map = solve_map_prob(norm_blue, best_of=p["best_of"])
                            q_map = 1.0 - p_map
                            raw_probs = {
                                "2-0": p_map ** 2,
                                "2-1": 2 * (p_map ** 2) * q_map,
                                "1-2": 2 * (q_map ** 2) * p_map,
                                "0-2": q_map ** 2
                            }
                            factor = 1.0 + max(0.0, margin)
                            if not cs_20: cs_20 = 1.0 / (raw_probs["2-0"] * factor)
                            if not cs_21: cs_21 = 1.0 / (raw_probs["2-1"] * factor)
                            if not cs_12: cs_12 = 1.0 / (raw_probs["1-2"] * factor)
                            if not cs_02: cs_02 = 1.0 / (raw_probs["0-2"] * factor)
                        except Exception:
                            pass
                
            show_kelly_for_market("Score 2-0", p["market_probs"]["2-0"], cs_20)
            show_kelly_for_market("Score 2-1", p["market_probs"]["2-1"], cs_21)
            show_kelly_for_market("Score 1-2", p["market_probs"]["1-2"], cs_12)
            show_kelly_for_market("Score 0-2", p["market_probs"]["0-2"], cs_02)
            
        print("   " + "-" * 50)
'''

match = re.search(r"def predict_schedule\(league=[\s\S]*?(?=if __name__ ==)", content)
if match:
    new_content = content[:match.start()] + data_func + "\n" + new_predict_schedule + "\n" + content[match.end():]
    with open("c:/Users/Admin/Documents/AI/Prediction Model/schedule_predict.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("schedule_predict.py updated")
else:
    print("Could not find predict_schedule")
