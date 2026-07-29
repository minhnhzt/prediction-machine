"""
llm_prepare_data.py — Compile LPL/LCK match data into conversational prompts for Qwen-2.5 fine-tuning.
"""

import os
import sqlite3
import json
import pandas as pd
from feature_engineering import build_feature_dataframe, DB_PATH

def prepare_llm_data(league="LPL", db_path=DB_PATH, train_ratio=0.80):
    print(f"[INFO] Fetching feature dataframe for {league}...")
    df = build_feature_dataframe(db_path, league_filter=league)
    if len(df) == 0:
        print(f"[ERROR] No matches found for league {league}.")
        return

    # Load team and champion names from DB
    conn = sqlite3.connect(db_path)
    teams = {row[0]: row[1] for row in conn.execute("SELECT Id, Name FROM Team").fetchall()}
    champions = {row[0]: row[1] for row in conn.execute("SELECT Id, Name FROM Champion").fetchall()}
    
    # Load picks for each match
    picks = conn.execute("SELECT MatchId, TeamId, ChampionId FROM PickBan WHERE IsBan = 0").fetchall()
    picks_map = {}
    for p in picks:
        mid, tid, cid = p[0], p[1], p[2]
        picks_map.setdefault(mid, {}).setdefault(tid, []).append(champions.get(cid, "Unknown"))
    
    conn.close()

    jsonl_data = []

    for _, row in df.iterrows():
        mid = int(row["MatchId"])
        blue_id = int(row["BlueTeamId"])
        red_id = int(row["RedTeamId"])
        blue_won = int(row["BlueTeamWin"]) == 1

        blue_name = teams.get(blue_id, f"Team_{blue_id}")
        red_name = teams.get(red_id, f"Team_{red_id}")

        blue_picks_list = picks_map.get(mid, {}).get(blue_id, [])
        red_picks_list = picks_map.get(mid, {}).get(red_id, [])

        # Skip matches without complete pick/ban data
        if len(blue_picks_list) < 5 or len(red_picks_list) < 5:
            continue

        blue_picks_str = ", ".join(blue_picks_list)
        red_picks_str = ", ".join(red_picks_list)

        # Build prompt
        prompt_text = (
            f"Match context:\n"
            f"Blue Team: {blue_name} (Elo: {row['Blue_Elo']:.0f}, ObjCtrl: {row['Blue_ObjCtrl']:.2f}, "
            f"AvgKills: {row['Blue_AvgKills']:.1f}, AvgDuration: {row['Blue_AvgDuration']:.0f}s, "
            f"AvgDragons: {row['Blue_AvgDragons']:.1f}, AvgTowers: {row['Blue_AvgTowers']:.1f}, "
            f"AvgGold: {row['Blue_AvgGold']:.0f})\n"
            f"Red Team: {red_name} (Elo: {row['Red_Elo']:.0f}, ObjCtrl: {row['Red_ObjCtrl']:.2f}, "
            f"AvgKills: {row['Red_AvgKills']:.1f}, AvgDuration: {row['Red_AvgDuration']:.0f}s, "
            f"AvgDragons: {row['Red_AvgDragons']:.1f}, AvgTowers: {row['Red_AvgTowers']:.1f}, "
            f"AvgGold: {row['Red_AvgGold']:.0f})\n\n"
            f"Draft picks:\n"
            f"Blue Team Picks: {blue_picks_str}\n"
            f"Red Team Picks: {red_picks_str}\n\n"
            f"Which team wins?"
        )

        winner_side = "Blue" if blue_won else "Red"

        messages = [
            {"role": "system", "content": "You are an expert League of Legends analyst. Predict the winner of the match based on ELO, historical stats, and the champion draft."},
            {"role": "user", "content": prompt_text},
            {"role": "assistant", "content": f"Winner: {winner_side}"}
        ]

        jsonl_data.append({"messages": messages})

    # Chronological split
    split_idx = int(len(jsonl_data) * train_ratio)
    train_data = jsonl_data[:split_idx]
    val_data = jsonl_data[split_idx:]

    # Write output files
    train_path = "llm_train.jsonl"
    val_path = "llm_val.jsonl"

    with open(train_path, "w", encoding="utf-8") as f:
        for item in train_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    with open(val_path, "w", encoding="utf-8") as f:
        for item in val_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[INFO] Successfully created {train_path} ({len(train_data)} rows) and {val_path} ({len(val_data)} rows).")

if __name__ == "__main__":
    prepare_llm_data(league="LPL")
