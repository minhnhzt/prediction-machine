import re
with open("c:/Users/Admin/Documents/AI/Prediction Model/backtest_betting.py", "r", encoding="utf-8") as f:
    content = f.read()

data_func = '''
def run_backtest_data(league="LPL", model_type="lr", initial_bankroll=1000.0, fractional=0.5, num_matches=50, margin=0.05) -> dict:
    if not os.path.isfile(DB_PATH):
        return {"error": f"Database not found at {DB_PATH}"}

    df = build_feature_dataframe(DB_PATH, league_filter=league)
    if len(df) < 60:
        return {"error": f"Not enough matches in database ({len(df)}) to run a 50-match backtest."}

    df = df.sort_values(by="Date").reset_index(drop=True)

    backtest_start_idx = len(df) - num_matches
    train_initial_df = df.iloc[:backtest_start_idx]
    test_df = df.iloc[backtest_start_idx:]

    conn = sqlite3.connect(DB_PATH)
    teams_dict = {}
    for tid, name in conn.execute("SELECT Id, Name FROM Team").fetchall():
        teams_dict[tid] = name

    real_odds_map = {}
    try:
        for row in conn.execute("SELECT BlueTeamName, RedTeamName, MatchDate, OddsBlue, OddsRed FROM MatchOdds").fetchall():
            key = (row[0].strip().upper(), row[1].strip().upper(), row[2])
            real_odds_map[key] = (row[3], row[4])
            key_rev = (row[1].strip().upper(), row[0].strip().upper(), row[2])
            real_odds_map[key_rev] = (row[4], row[3])
    except Exception:
        pass
    conn.close()

    real_odds_used = 0
    sim_odds_used = 0

    bankroll = initial_bankroll
    bankroll_history = [bankroll]
    bets_placed = 0
    bets_won = 0
    total_wagered = 0.0
    max_bankroll = bankroll
    max_drawdown = 0.0

    bets_data = []

    for i in range(len(test_df)):
        current_train = df.iloc[:backtest_start_idx + i]
        current_row = test_df.iloc[i]

        X_train = current_train[FEATURE_COLS].values
        y_train = current_train[TARGET_COL].values
        X_test = current_row[FEATURE_COLS].values.reshape(1, -1)
        actual_win = int(current_row[TARGET_COL])

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        model = get_model(model_type)
        model.fit(X_train_scaled, y_train)

        p_blue = float(model.predict_proba(X_test_scaled)[0][1])
        p_red = 1.0 - p_blue

        blue_id = int(current_row["BlueTeamId"])
        red_id = int(current_row["RedTeamId"])
        blue_name = teams_dict.get(blue_id, f"Team_{blue_id}")
        red_name = teams_dict.get(red_id, f"Team_{red_id}")

        date_str = str(current_row["Date"])
        odds_source = "SIM"
        lookup_key = (blue_name.strip().upper(), red_name.strip().upper(), date_str)

        if lookup_key in real_odds_map:
            odds_blue, odds_red = real_odds_map[lookup_key]
            odds_source = "REAL"
            real_odds_used += 1
        else:
            blue_elo = current_row["Blue_Elo"]
            red_elo = current_row["Red_Elo"]
            bookie_prob_blue = 1.0 / (1.0 + 10 ** ((red_elo - blue_elo) / 400.0))
            bookie_prob_red = 1.0 - bookie_prob_blue
            odds_blue = max(1.01, 1.0 / (bookie_prob_blue * (1.0 + margin)))
            odds_red = max(1.01, 1.0 / (bookie_prob_red * (1.0 + margin)))
            sim_odds_used += 1

        edge_blue = p_blue * odds_blue - 1.0
        edge_red = p_red * odds_red - 1.0

        bet_side = None
        chosen_odds = 0.0
        chosen_prob = 0.0

        if edge_blue > 0:
            bet_side = "Blue"
            chosen_odds = odds_blue
            chosen_prob = p_blue
        elif edge_red > 0:
            bet_side = "Red"
            chosen_odds = odds_red
            chosen_prob = p_red

        wager = 0.0
        result_str = "SKIP"
        pnl = 0.0

        if bet_side is not None and bankroll > 0:
            kc = kelly_criterion(chosen_prob, chosen_odds, bankroll=bankroll, fractional=fractional)
            wager = kc.wager_amount
            
            if wager > 0:
                bets_placed += 1
                total_wagered += wager
                is_win = (actual_win == 1 and bet_side == "Blue") or (actual_win == 0 and bet_side == "Red")
                
                if is_win:
                    profit = wager * (chosen_odds - 1.0)
                    bankroll += profit
                    bets_won += 1
                    result_str = "WIN"
                    pnl = profit
                else:
                    bankroll -= wager
                    result_str = "LOSS"
                    pnl = -wager

        bankroll_history.append(bankroll)
        max_bankroll = max(max_bankroll, bankroll)
        dd = (max_bankroll - bankroll) / max_bankroll if max_bankroll > 0 else 0.0
        max_drawdown = max(max_drawdown, dd)

        predicted_winner = blue_name if p_blue >= 0.5 else red_name
        actual_winner_name = blue_name if actual_win == 1 else red_name

        bets_data.append({
            "match_num": i + 1,
            "blue": blue_name,
            "red": red_name,
            "date": date_str,
            "predicted_winner": predicted_winner,
            "actual_winner": actual_winner_name,
            "win_prob": p_blue if p_blue >= 0.5 else p_red,
            "blue_prob": p_blue,
            "red_prob": p_red,
            "odds_blue": odds_blue,
            "odds_red": odds_red,
            "odds": chosen_odds if bet_side else (odds_blue if p_blue >= 0.5 else odds_red),
            "odds_type": odds_source,
            "wager": wager,
            "pnl": pnl,
            "bankroll_after": bankroll,
            "result": result_str,
            "bet_side": bet_side
        })

    total_roi = (bankroll - initial_bankroll) / initial_bankroll if initial_bankroll > 0 else 0
    win_rate = (bets_won / bets_placed) if bets_placed > 0 else 0.0

    return {
        "summary": {
            "initial_bankroll": initial_bankroll,
            "final_bankroll": bankroll,
            "roi_pct": total_roi * 100,
            "win_rate_pct": win_rate * 100,
            "total_bets": bets_placed,
            "wins": bets_won,
            "losses": bets_placed - bets_won,
            "skipped": len(test_df) - bets_placed,
            "max_drawdown_pct": max_drawdown * 100,
            "real_odds_count": real_odds_used,
            "sim_odds_count": sim_odds_used,
            "total_wagered": total_wagered
        },
        "bankroll_history": bankroll_history,
        "bets": bets_data
    }
'''

new_run_backtest = '''
def run_backtest(league="LPL", model_type="lr", initial_bankroll=1000.0, fractional=0.5, num_matches=50, margin=0.05):
    print("=" * 70)
    print(f"  STARTING KELLY BETTING BACKTEST SIMULATOR ({league})")
    print(f"  Model: {model_type.upper()} | Bankroll: ${initial_bankroll:,.2f} | Kelly: {fractional}x | Margin: {margin:.1%}")
    print("=" * 70)

    data = run_backtest_data(league, model_type, initial_bankroll, fractional, num_matches, margin)
    
    if "error" in data:
        print(f"[ERROR] {data['error']}")
        return

    print(f"[INFO] Initial Training Set Size: ...")
    print(f"[INFO] Backtesting on the next {num_matches} games chronologically...")

    print(f"\\n{'Date':<11} | {'Matchup':<30} | {'Model Prob':<12} | {'Bookie Odds':<17} | {'Wager':<14} | {'Result':<6} | {'New Bankroll'}")
    print("-" * 120)

    for b in data["bets"]:
        matchup_str = f"{b['blue']} vs {b['red']}"
        prob_str = f"B:{b['blue_prob']:.1%} R:{b['red_prob']:.1%}"
        odds_str = f"[{b['odds_type']}] B:{b['odds_blue']:.2f} R:{b['odds_red']:.2f}"
        wager_str = f"${b['wager']:.2f} ({b['bet_side']})" if b['wager'] > 0 else "No Edge"
        print(f"{b['date']:<11} | {matchup_str:<30} | {prob_str:<12} | {odds_str:<17} | {wager_str:<14} | {b['result']:<6} | ${b['bankroll_after']:,.2f}")

    s = data["summary"]
    
    print("=" * 70)
    print("  BACKTEST RESULTS SUMMARY")
    print("=" * 70)
    print(f"  * Initial Capital  : ${s['initial_bankroll']:,.2f}")
    print(f"  * Final Capital    : ${s['final_bankroll']:,.2f}")
    print(f"  * Total Return     : {s['roi_pct']/100:+.2%}")
    print(f"  * Bets Placed      : {s['total_bets']} / {num_matches} matches")
    print(f"  * Bets Won         : {s['wins']} ({s['win_rate_pct']/100:.1%})")
    print(f"  * Total Wagered    : ${s['total_wagered']:,.2f}")
    print(f"  * Maximum Drawdown : {s['max_drawdown_pct']/100:.1%}")
    print(f"  * Odds Source      : {s['real_odds_count']} REAL / {s['sim_odds_count']} SIMULATED")
    print("=" * 70)

    bankroll_history = data["bankroll_history"]
    if len(bankroll_history) > 1:
        print("\\n  BANKROLL PROGRESSION CHART:")
        steps = 15
        val_min = min(bankroll_history)
        val_max = max(bankroll_history)
        val_range = val_max - val_min if val_max > val_min else 1.0
        
        for step in range(steps, -1, -1):
            threshold = val_min + (step / steps) * val_range
            line_str = f"  ${threshold:>8.2f} | "
            for val in bankroll_history:
                if val >= threshold:
                    line_str += "#"
                else:
                    line_str += " "
            print(line_str)
        print(" " * 12 + "+" + "-" * len(bankroll_history))
'''

match = re.search(r"def run_backtest\(league=[\s\S]*?(?=if __name__ ==)", content)
if match:
    new_content = content[:match.start()] + data_func + "\n" + new_run_backtest + "\n" + content[match.end():]
    with open("c:/Users/Admin/Documents/AI/Prediction Model/backtest_betting.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("backtest_betting.py updated")
else:
    print("Could not find run_backtest")
