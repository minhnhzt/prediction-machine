"""
backtest_betting.py — Walk-forward historical backtesting simulator for the Kelly Criterion betting system.
"""

import os
import sys
import time
import sqlite3
import argparse
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

# Add root directory to python path
sys.path.insert(0, os.path.dirname(__file__))

from feature_engineering import build_feature_dataframe, DB_PATH, FEATURE_COLS, TARGET_COL
from model import train_and_evaluate, PyTorchTabAttentionClassifier
from kelly_criterion import kelly_criterion

# Import optional classifiers safely
try:
    from xgboost import XGBClassifier
except (ImportError, OSError):
    XGBClassifier = None

try:
    from lightgbm import LGBMClassifier
except (ImportError, OSError):
    LGBMClassifier = None

try:
    from autogluon_model import AutoGluonClassifier
except ImportError:
    AutoGluonClassifier = None


def get_model(model_type, random_state=42):
    if model_type == "lr":
        return LogisticRegression(C=0.1, solver="liblinear", random_state=random_state)
    elif model_type == "rf":
        return RandomForestClassifier(max_depth=6, n_estimators=100, random_state=random_state, n_jobs=-1)
    elif model_type == "xgboost" and XGBClassifier is not None:
        return XGBClassifier(max_depth=4, n_estimators=100, learning_rate=0.05, eval_metric="logloss", random_state=random_state, n_jobs=-1)
    elif model_type == "lightgbm" and LGBMClassifier is not None:
        return LGBMClassifier(max_depth=4, n_estimators=100, learning_rate=0.05, verbose=-1, random_state=random_state, n_jobs=-1)
    elif model_type == "tabattention":
        return PyTorchTabAttentionClassifier(d_model=16, epochs=30, lr=0.01, nhead=2)
    else:
        # Fallback to LR
        return LogisticRegression(C=0.1, solver="liblinear", random_state=random_state)


def run_backtest(league="LPL", model_type="lr", initial_bankroll=1000.0, fractional=0.5, num_matches=50, margin=0.05):
    print("=" * 70)
    print(f"  STARTING KELLY BETTING BACKTEST SIMULATOR ({league})")
    print(f"  Model: {model_type.upper()} | Bankroll: ${initial_bankroll:,.2f} | Kelly: {fractional}x | Margin: {margin:.1%}")
    print("=" * 70)

    if not os.path.isfile(DB_PATH):
        print(f"[ERROR] Database not found at {DB_PATH}. Run real_data_pipeline.py first.")
        return

    # Load complete dataframe
    df = build_feature_dataframe(DB_PATH, league_filter=league)
    if len(df) < 60:
        print(f"[ERROR] Not enough matches in database ({len(df)}) to run a 50-match backtest.")
        return

    # Sort matches chronologically
    df = df.sort_values(by="Date").reset_index(drop=True)

    # We will backtest on the last `num_matches` games
    backtest_start_idx = len(df) - num_matches
    train_initial_df = df.iloc[:backtest_start_idx]
    test_df = df.iloc[backtest_start_idx:]

    print(f"[INFO] Initial Training Set Size: {len(train_initial_df)} games")
    print(f"[INFO] Backtesting on the next {len(test_df)} games chronologically...")

    # Load Team Name mappings from SQLite
    conn = sqlite3.connect(DB_PATH)
    teams_dict = {}
    for tid, name in conn.execute("SELECT Id, Name FROM Team").fetchall():
        teams_dict[tid] = name

    # Pre-load all real odds from MatchOdds table for fast lookup
    real_odds_map = {}  # key: (blue_name_lower, red_name_lower, date) -> (odds_blue, odds_red)
    try:
        for row in conn.execute("SELECT BlueTeamName, RedTeamName, MatchDate, OddsBlue, OddsRed FROM MatchOdds").fetchall():
            key = (row[0].strip().upper(), row[1].strip().upper(), row[2])
            real_odds_map[key] = (row[3], row[4])
            # Also store reversed key for matching flexibility
            key_rev = (row[1].strip().upper(), row[0].strip().upper(), row[2])
            real_odds_map[key_rev] = (row[4], row[3])
    except Exception:
        pass  # Table might not exist yet
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

    print(f"\n{'Date':<11} | {'Matchup':<30} | {'Model Prob':<12} | {'Bookie Odds':<17} | {'Wager':<14} | {'Result':<6} | {'New Bankroll'}")
    print("-" * 120)

    # Chronological Walk-Forward Simulation
    for i in range(len(test_df)):
        # 1. Split training set dynamically (preventing any future data leakage)
        current_train = df.iloc[:backtest_start_idx + i]
        current_row = test_df.iloc[i]

        X_train = current_train[FEATURE_COLS].values
        y_train = current_train[TARGET_COL].values
        X_test = current_row[FEATURE_COLS].values.reshape(1, -1)
        actual_win = int(current_row[TARGET_COL]) # 1 = Blue win, 0 = Red win (BlueTeamWin)

        # 2. Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # 3. Train model on historical data
        model = get_model(model_type)
        model.fit(X_train_scaled, y_train)

        # 4. Predict probability for the current match
        p_blue = float(model.predict_proba(X_test_scaled)[0][1])
        p_red = 1.0 - p_blue

        # 5. Extract team names
        blue_id = int(current_row["BlueTeamId"])
        red_id = int(current_row["RedTeamId"])
        blue_name = teams_dict.get(blue_id, f"Team_{blue_id}")
        red_name = teams_dict.get(red_id, f"Team_{red_id}")
        matchup_str = f"{blue_name} vs {red_name}"

        # 6. Try to use REAL bookmaker odds from MatchOdds table first
        date_str = str(current_row["Date"])
        odds_source = "SIM"
        lookup_key = (blue_name.strip().upper(), red_name.strip().upper(), date_str)

        if lookup_key in real_odds_map:
            odds_blue, odds_red = real_odds_map[lookup_key]
            odds_source = "REAL"
            real_odds_used += 1
        else:
            # Fallback: Simulate bookmaker odds using ELO difference
            blue_elo = current_row["Blue_Elo"]
            red_elo = current_row["Red_Elo"]
            bookie_prob_blue = 1.0 / (1.0 + 10 ** ((red_elo - blue_elo) / 400.0))
            bookie_prob_red = 1.0 - bookie_prob_blue
            odds_blue = max(1.01, 1.0 / (bookie_prob_blue * (1.0 + margin)))
            odds_red = max(1.01, 1.0 / (bookie_prob_red * (1.0 + margin)))
            sim_odds_used += 1

        # 7. Evaluate betting opportunities
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

        # 8. Apply Kelly Criterion sizing
        wager = 0.0
        result_str = "SKIP"
        if bet_side is not None and bankroll > 0:
            kc = kelly_criterion(chosen_prob, chosen_odds, bankroll=bankroll, fractional=fractional)
            wager = kc.wager_amount
            
            # Wager execution
            if wager > 0:
                bets_placed += 1
                total_wagered += wager
                is_win = (actual_win == 1 and bet_side == "Blue") or (actual_win == 0 and bet_side == "Red")
                
                if is_win:
                    profit = wager * (chosen_odds - 1.0)
                    bankroll += profit
                    bets_won += 1
                    result_str = f"WIN"
                else:
                    bankroll -= wager
                    result_str = f"LOSS"

        # Update stats
        bankroll_history.append(bankroll)
        max_bankroll = max(max_bankroll, bankroll)
        dd = (max_bankroll - bankroll) / max_bankroll if max_bankroll > 0 else 0.0
        max_drawdown = max(max_drawdown, dd)

        # Log details with odds source indicator
        prob_str = f"B:{p_blue:.1%} R:{p_red:.1%}"
        odds_str = f"[{odds_source}] B:{odds_blue:.2f} R:{odds_red:.2f}"
        wager_str = f"${wager:.2f} ({bet_side})" if wager > 0 else "No Edge"
        print(f"{date_str:<11} | {matchup_str:<30} | {prob_str:<12} | {odds_str:<17} | {wager_str:<14} | {result_str:<6} | ${bankroll:,.2f}")

    # Final summary
    total_roi = (bankroll - initial_bankroll) / initial_bankroll
    win_rate = (bets_won / bets_placed) if bets_placed > 0 else 0.0

    print("=" * 70)
    print("  BACKTEST RESULTS SUMMARY")
    print("=" * 70)
    print(f"  * Initial Capital  : ${initial_bankroll:,.2f}")
    print(f"  * Final Capital    : ${bankroll:,.2f}")
    print(f"  * Total Return     : {total_roi:+.2%}")
    print(f"  * Bets Placed      : {bets_placed} / {num_matches} matches")
    print(f"  * Bets Won         : {bets_won} ({win_rate:.1%})")
    print(f"  * Total Wagered    : ${total_wagered:,.2f}")
    print(f"  * Maximum Drawdown : {max_drawdown:.1%}")
    print(f"  * Odds Source      : {real_odds_used} REAL / {sim_odds_used} SIMULATED")
    print("=" * 70)

    # Print ASCII chart
    if len(bankroll_history) > 1:
        print("\n  BANKROLL PROGRESSION CHART:")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run chronological betting backtests.")
    parser.add_argument("--league", type=str, default="LPL", choices=["LPL", "LCK"], help="League to backtest")
    parser.add_argument("--model", type=str, default="lr", choices=["lr", "rf", "xgboost", "lightgbm", "tabattention"], help="Model to evaluate")
    parser.add_argument("--capital", type=float, default=1000.0, help="Initial bankroll")
    parser.add_argument("--kelly", type=float, default=0.5, help="Kelly Criterion multiplier (fractional Kelly)")
    parser.add_argument("--matches", type=int, default=50, help="Number of games to simulate")
    parser.add_argument("--margin", type=float, default=0.05, help="Simulated bookmaker margin")
    args = parser.parse_args()

    run_backtest(
        league=args.league,
        model_type=args.model,
        initial_bankroll=args.capital,
        fractional=args.kelly,
        num_matches=args.matches,
        margin=args.margin
    )
