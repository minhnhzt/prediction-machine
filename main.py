"""
main.py — End-to-end orchestrator for the LPL/LCK Prediction System.
"""

import sys
import os
import sqlite3
import argparse

# Force UTF-8 encoding on stdout and stderr to avoid Windows console Unicode errors
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

from feature_engineering import build_feature_dataframe, DB_PATH
from model import train_and_evaluate, predict_hypothetical
from kelly_criterion import kelly_criterion
from benchmark import run_benchmark
from schedule_predict import predict_schedule

def run_interactive_calculator(league: str, model_type: str, db_path: str) -> None:
    import datetime
    from schedule_predict import (
        fetch_schedule, fetch_bovada_odds, match_bovada_teams,
        parse_bovada_markets_for_event, calculate_secondary_markets,
        train_model_for_league, get_team_features, normalize_name
    )
    from feature_engineering import get_latest_team_stats
    import numpy as np
    from kelly_criterion import kelly_criterion

    print("=" * 60)
    print(f"  INTERACTIVE BETTING CALCULATOR ({league})")
    print("=" * 60)

    # 1. Fetch schedule
    try:
        schedule_data = fetch_schedule(use_cache=True)
    except Exception:
        print("[ERROR] Cannot retrieve schedule.")
        return

    events = schedule_data.get("data", {}).get("schedule", {}).get("events", [])
    if not events:
        print("No events found in schedule.")
        return

    # Filter events
    now = datetime.datetime.now(datetime.timezone.utc)
    three_days_later = now + datetime.timedelta(days=3)
    filtered = []
    
    for ev in events:
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
            
        filtered.append(ev)
        
    if not filtered:
        print(f"No upcoming {league} matches found in the schedule.")
        return
        
    print("\nSelect a match to analyze:")
    for idx, ev in enumerate(filtered):
        teams = ev.get("match", {}).get("teams", [])
        blue = teams[0].get("name")
        red = teams[1].get("name")
        print(f"  [{idx + 1}] {blue} vs {red}")
        
    # Get user selection
    try:
        choice = input("\nEnter match number (or 'q' to quit): ").strip()
        if choice.lower() == 'q':
            return
        idx = int(choice) - 1
        if idx < 0 or idx >= len(filtered):
            print("Invalid match selection.")
            return
    except ValueError:
        print("Invalid input.")
        return
        
    selected_ev = filtered[idx]
    teams = selected_ev.get("match", {}).get("teams", [])
    blue_api_name = teams[0].get("name")
    red_api_name = teams[1].get("name")
    
    print(f"\n[INFO] Training model on historical {league} data...")
    latest_stats, name_to_id = get_latest_team_stats(db_path, league_filter=league)
    model, scaler = train_model_for_league(league, model_type=model_type, db_path=db_path)
    
    blue_db_name = normalize_name(blue_api_name)
    red_db_name = normalize_name(red_api_name)
    
    blue_feats, _ = get_team_features(blue_db_name, latest_stats, name_to_id)
    red_feats, _ = get_team_features(red_db_name, latest_stats, name_to_id)
    
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
    
    # Fetch Bovada odds to pre-populate live odds
    bovada_events = fetch_bovada_odds()
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
            
    bovada_odds = None
    if matched_bev:
        bovada_odds = parse_bovada_markets_for_event(matched_bev, b_team_a, b_team_b)
        
    market_probs = calculate_secondary_markets(proba[1], best_of=3)
    
    print(f"\nMatch: {blue_api_name} vs {red_api_name}")
    print(f"Model P({blue_api_name} Win) = {proba[1]:.2%}")
    print(f"Model P({red_api_name} Win) = {proba[0]:.2%}")
    
    # List outcomes, their model probabilities, and fair odds
    outcomes = []
    
    # 1. Winner
    outcomes.append({
        "label": f"{blue_api_name} Winner",
        "prob": proba[1],
        "live": bovada_odds["ml"].get(b_team_a if direction == "direct" else b_team_b) if bovada_odds else None
    })
    outcomes.append({
        "label": f"{red_api_name} Winner",
        "prob": proba[0],
        "live": bovada_odds["ml"].get(b_team_b if direction == "direct" else b_team_a) if bovada_odds else None
    })
    
    # 2. Handicap (point spread)
    hc_blue_val = 1.5
    hc_red_val = -1.5
    live_hc_blue = None
    live_hc_red = None
    
    if bovada_odds:
        blue_key = b_team_a if direction == "direct" else b_team_b
        red_key = b_team_b if direction == "direct" else b_team_a
        
        hc_blue_info = bovada_odds["handicap"].get(blue_key, {})
        hc_red_info = bovada_odds["handicap"].get(red_key, {})
        
        live_hc_blue = hc_blue_info.get("price")
        hc_blue_val = hc_blue_info.get("handicap", 1.5)
        live_hc_red = hc_red_info.get("price")
        hc_red_val = hc_red_info.get("handicap", -1.5)
        
    blue_hc_prob = market_probs["Blue +1.5"] if hc_blue_val == 1.5 else market_probs["Blue -1.5"]
    red_hc_prob = market_probs["Red +1.5"] if hc_red_val == 1.5 else market_probs["Red -1.5"]
    
    outcomes.append({
        "label": f"{blue_api_name} Handicap ({hc_blue_val:+.1f})",
        "prob": blue_hc_prob,
        "live": live_hc_blue
    })
    outcomes.append({
        "label": f"{red_api_name} Handicap ({hc_red_val:+.1f})",
        "prob": red_hc_prob,
        "live": live_hc_red
    })
    
    # 3. Total Maps
    live_over = bovada_odds["total"].get("Over", {}).get("price") if bovada_odds else None
    live_under = bovada_odds["total"].get("Under", {}).get("price") if bovada_odds else None
    outcomes.append({
        "label": "Total Maps Over 2.5",
        "prob": market_probs["Over 2.5"],
        "live": live_over
    })
    outcomes.append({
        "label": "Total Maps Under 2.5",
        "prob": market_probs["Under 2.5"],
        "live": live_under
    })
    
    # 4. Correct Score
    if bovada_odds:
        blue_key = b_team_a if direction == "direct" else b_team_b
        red_key = b_team_b if direction == "direct" else b_team_a
        
        live_20 = bovada_odds["correct_score"].get(f"{blue_key} 2-0")
        live_21 = bovada_odds["correct_score"].get(f"{blue_key} 2-1")
        live_12 = bovada_odds["correct_score"].get(f"{red_key} 2-1")
        live_02 = bovada_odds["correct_score"].get(f"{red_key} 2-0")
    else:
        live_20 = live_21 = live_12 = live_02 = None
    
    outcomes.append({"label": "Score 2-0", "prob": market_probs["2-0"], "live": live_20})
    outcomes.append({"label": "Score 2-1", "prob": market_probs["2-1"], "live": live_21})
    outcomes.append({"label": "Score 1-2", "prob": market_probs["1-2"], "live": live_12})
    outcomes.append({"label": "Score 0-2", "prob": market_probs["0-2"], "live": live_02})
    
    print("\nBetting Markets:")
    for idx, out in enumerate(outcomes):
        fair = 1.0 / out["prob"] if out["prob"] > 0 else float('inf')
        live_str = f"{out['live']:.2f}" if out["live"] else "N/A"
        print(f"  [{idx + 1}] {out['label']:<30} | Prob: {out['prob']:>6.2%} | Fair Odds: {fair:>5.2f} | Bovada Live Odds: {live_str}")
        
    try:
        m_choice = input("\nSelect a market option by index (or 'q' to quit): ").strip()
        if m_choice.lower() == 'q':
            return
        m_idx = int(m_choice) - 1
        if m_idx < 0 or m_idx >= len(outcomes):
            print("Invalid selection.")
            return
    except ValueError:
        print("Invalid input.")
        return
        
    selected_out = outcomes[m_idx]
    print(f"\nSelected Option: {selected_out['label']}")
    print(f"Model Probability: {selected_out['prob']:.2%}")
    print(f"Fair Odds: {1.0 / selected_out['prob']:.2f}")
    
    # Prompt for odds
    default_odds_str = f" [default: {selected_out['live']:.2f}]" if selected_out['live'] else ""
    odds_inp = input(f"Enter the bookmaker decimal odds you see (e.g. on Stake){default_odds_str}: ").strip()
    if not odds_inp:
        if selected_out['live']:
            odds_val = selected_out['live']
        else:
            print("No odds entered. Quitting.")
            return
    else:
        try:
            odds_val = float(odds_inp)
        except ValueError:
            print("Invalid odds value.")
            return
            
    # Prompt for bankroll
    bankroll_inp = input("Enter your bankroll in USD [default: $1000]: ").strip()
    bankroll_val = 1000.0
    if bankroll_inp:
        try:
            bankroll_val = float(bankroll_inp)
        except ValueError:
            print("Invalid bankroll value.")
            return
            
    # Prompt for Kelly fraction
    frac_inp = input("Enter Kelly fraction (1.0 = Full, 0.5 = Half, 0.25 = Quarter) [default: 0.5]: ").strip()
    frac_val = 0.5
    if frac_inp:
        try:
            frac_val = float(frac_inp)
        except ValueError:
            print("Invalid fraction value.")
            return
            
    # Calculate Kelly
    res = kelly_criterion(selected_out["prob"], odds_val, bankroll=bankroll_val, fractional=frac_val)
    print("\n" + "=" * 40)
    print("  KELLY CRITERION RECOMMENDATION")
    print("=" * 40)
    summary_clean = res.summary().replace("✅", "[OK]").replace("❌", "[SKIP]")
    print(summary_clean)
    print("=" * 40)

def main() -> None:
    parser = argparse.ArgumentParser(description="LPL/LCK Match Prediction System — End-to-End Pipeline")
    parser.add_argument("--league", type=str, default="LPL", choices=["LPL", "LCK"], help="League to focus on (LPL or LCK)")
    parser.add_argument("--model", type=str, default="rf", choices=["lr", "rf", "xgboost", "lightgbm", "tabattention", "autogluon"], help="Model type to use")
    parser.add_argument("--tune", action="store_true", help="Enable hyperparameter tuning via GridSearchCV")
    parser.add_argument("--benchmark", action="store_true", help="Run the full benchmarking suite for the selected league")
    parser.add_argument("--schedule", action="store_true", help="Predict outcomes for matches in the upcoming 3 days")
    parser.add_argument("--markets", action="store_true", help="Show all secondary betting markets in schedule mode")
    parser.add_argument("--interactive", action="store_true", help="Start the interactive betting calculator")
    parser.add_argument("--no-cache", action="store_true", help="Force refresh of live schedule, bypassing local cache")
    
    args = parser.parse_args()

    # ── Orchestrate Modes ───────────────────────────────────────────────────
    if args.benchmark:
        run_benchmark(league=args.league)
        return
        
    if args.interactive:
        run_interactive_calculator(league=args.league, model_type=args.model, db_path=DB_PATH)
        return
        
    if args.schedule:
        predict_schedule(
            league=args.league,
            model_type=args.model,
            use_cache=not args.no_cache,
            show_markets=args.markets
        )
        return

    # ── Default Flow: Single Model Train, Evaluate & Predict ────────────────
    print("╔" + "═" * 58 + "╗")
    print(f"║   {args.league} MATCH PREDICTION SYSTEM — {args.model.upper()} PIPELINE{' ' * (31 - len(args.league) - len(args.model))} ║")
    print("╚" + "═" * 58 + "╝\n")

    # ── Stage 1: Data Check ───────────────────────────────────────────────
    print("━" * 60)
    print("  STAGE 1 ▸ Data Check")
    print("━" * 60)
    db_path = DB_PATH
    if not os.path.isfile(db_path):
        print(f"  [ERROR] Database not found at {db_path}. Run real_data_pipeline.py first:")
        print('     python real_data_pipeline.py --csv "data\\<file>.csv" --league LPL --fresh')
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    match_count = conn.execute("SELECT COUNT(*) FROM Match").fetchone()[0]
    conn.close()
    print(f"  [OK] Database: {db_path}")
    print(f"  [OK] Total Matches in DB: {match_count:,}")

    # ── Stage 2: Feature Engineering ──────────────────────────────────────
    print("\n" + "━" * 60)
    print("  STAGE 2 ▸ Feature Engineering")
    print("━" * 60)
    df = build_feature_dataframe(db_path, league_filter=args.league)
    if len(df) == 0:
        print(f"  [ERROR] No matches found for league {args.league} in the database.")
        sys.exit(1)
        
    print(f"\n   Sample rows (showing top 3):\n{df.head(3).to_string(index=False)}\n")

    # ── Stage 3: Model Training & Evaluation ──────────────────────────────
    print("━" * 60)
    print("  STAGE 3 ▸ Model Training & Evaluation")
    print("━" * 60)
    model, scaler, metrics = train_and_evaluate(df, model_type=args.model, tune=args.tune)

    # ── Stage 4: Hypothetical Match ───────────────────────────────────────
    print("\n" + "━" * 60)
    print("  STAGE 4 ▸ Hypothetical Match Prediction")
    print("━" * 60)
    prediction = predict_hypothetical(
        model,
        scaler,
        blue_elo=1600.0,
        red_elo=1500.0,
        blue_obj=0.60,
        red_obj=0.45,
        blue_avg_kills=16.0,
        red_avg_kills=14.0,
        blue_avg_dur=1900.0,
        red_avg_dur=2000.0,
        blue_avg_dragons=3.0,
        red_avg_dragons=2.1,
        blue_avg_towers=7.2,
        red_avg_towers=5.0,
        blue_avg_gold=57000.0,
        red_avg_gold=53000.0,
        blue_draft_wr=0.52,
        red_draft_wr=0.48
    )

    # ── Stage 5: Kelly Criterion Bet Sizing ───────────────────────────────
    print("\n" + "━" * 60)
    print("  STAGE 5 ▸ Kelly Criterion — Bankroll Management")
    print("━" * 60)
    blue_prob = prediction["blue_win_prob"]
    bankroll = 10_000.0
    odds = 1.85

    print(f"\n   Model P(Blue Win) = {blue_prob:.2%}")
    print(f"   Bookmaker Odds    = {odds}")
    print(f"   Bankroll          = ${bankroll:,.2f}\n")

    for label, frac in [("Full Kelly", 1.0), ("Half Kelly", 0.5), ("Quarter Kelly", 0.25)]:
        result = kelly_criterion(
            win_probability=blue_prob,
            decimal_odds=odds,
            bankroll=bankroll,
            fractional=frac,
        )
        print(f"   ── {label} {'─' * (42 - len(label))}")
        summary_clean = result.summary().replace("✅", "[OK]").replace("❌", "[SKIP]")
        print(f"   {summary_clean}\n")

    print("╔" + "═" * 58 + "╗")
    print("║   PIPELINE COMPLETE                                      ║")
    print("╚" + "═" * 58 + "╝")

if __name__ == "__main__":
    main()
