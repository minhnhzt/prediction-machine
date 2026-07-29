"""
feature_engineering.py — Extract core features from the relational DB.

Features (per team, computed *prior* to each match):
  1. Elo_Rating       – Standard Elo (K=32, base 1500)
  2. Objective_Control– Combined First Blood, First Dragon, First Tower rate (0–1 each, averaged)
  3. Avg_Kills        – Historical average kills per game
  4. Avg_Game_Duration– Historical average game duration (seconds)
  5. Avg_Dragons      - Historical average dragons per game
  6. Avg_Towers       - Historical average towers per game
  7. Avg_Gold         - Historical average total gold per game
  8. DraftWinRate     - Historical average win rate of picked champions

Returns a Pandas DataFrame ready for model training.
"""

import sqlite3
import os
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "lpl_prediction.db")

# ── Elo helpers ──────────────────────────────────────────────────────────────
DEFAULT_ELO = 1500.0
K_FACTOR = 32.0


def _expected_score(elo_a: float, elo_b: float) -> float:
    """Standard logistic expected-score formula."""
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def _update_elo(
    elo_a: float, elo_b: float, a_won: bool
) -> tuple[float, float]:
    """Return updated (elo_a, elo_b) after a single match."""
    ea = _expected_score(elo_a, elo_b)
    eb = 1.0 - ea
    sa = 1.0 if a_won else 0.0
    sb = 1.0 - sa
    return (
        elo_a + K_FACTOR * (sa - ea),
        elo_b + K_FACTOR * (sb - eb),
    )


# ── Core feature builder ────────────────────────────────────────────────────
def build_feature_dataframe(db_path: str = DB_PATH, league_filter: str | None = None) -> pd.DataFrame:
    """
    Walk matches in chronological order, compute rolling features for each
    team *before* the match is played, then record the outcome.

    Parameters
    ----------
    db_path : str
        Path to SQLite database.
    league_filter : str, optional
        e.g. 'LPL' or 'LCK'. If provided, filters by tournament name prefix.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # ── Load matches ordered chronologically ──────────────────────────────
    if league_filter:
        matches = conn.execute(
            """SELECT m.Id, m.Date, m.BlueTeamId, m.RedTeamId, m.WinnerId,
                      m.GameDuration
               FROM Match m
               WHERE m.Tournament LIKE ?
               ORDER BY m.Date, m.Id""",
            (f"{league_filter}%",)
        ).fetchall()
    else:
        matches = conn.execute(
            """SELECT m.Id, m.Date, m.BlueTeamId, m.RedTeamId, m.WinnerId,
                      m.GameDuration
               FROM Match m
               ORDER BY m.Date, m.Id"""
        ).fetchall()

    # ── Load all MatchDetail rows into a lookup ───────────────────────────
    details = conn.execute(
        "SELECT MatchId, TeamId, TotalKills, GoldDiff15, FirstBlood, FirstDragon, "
        "FirstTower, Dragons, Heralds, Barons, Towers, TotalGold "
        "FROM MatchDetail"
    ).fetchall()
    
    detail_map: dict[int, dict[int, dict]] = {}
    for d in details:
        mid = d["MatchId"]
        tid = d["TeamId"]
        detail_map.setdefault(mid, {})[tid] = {
            "TotalKills": d["TotalKills"],
            "GoldDiff15": d["GoldDiff15"],
            "FirstBlood": d["FirstBlood"],
            "FirstDragon": d["FirstDragon"],
            "FirstTower": d["FirstTower"],
            "Dragons": d["Dragons"],
            "Heralds": d["Heralds"],
            "Barons": d["Barons"],
            "Towers": d["Towers"],
            "TotalGold": d["TotalGold"],
        }

    # ── Load all Picks from PickBan table (IsBan = 0) ─────────────────────
    picks = conn.execute(
        "SELECT MatchId, TeamId, ChampionId FROM PickBan WHERE IsBan = 0"
    ).fetchall()
    picks_map: dict[int, dict[int, list[int]]] = {}
    for p in picks:
        mid = p["MatchId"]
        tid = p["TeamId"]
        cid = p["ChampionId"]
        picks_map.setdefault(mid, {}).setdefault(tid, []).append(cid)

    conn.close()

    # ── Accumulators per team ─────────────────────────────────────────────
    elo: dict[int, float] = {}             # team_id → current Elo
    fb_hist: dict[int, list[int]] = {}     # team_id → [0/1]
    fd_hist: dict[int, list[int]] = {}     # team_id → [0/1]
    kills_hist: dict[int, list[int]] = {}  # team_id → [total_kills]
    dur_hist: dict[int, list[int]] = {}    # team_id → [game_duration_s]
    ft_hist: dict[int, list[int]] = {}     # team_id -> [0/1] first tower
    dragons_hist: dict[int, list[int]] = {} # team_id -> [dragons per game]
    towers_hist: dict[int, list[int]] = {}  # team_id -> [towers per game]
    gold_hist: dict[int, list[int]] = {}    # team_id -> [total gold per game]

    # Champion accumulators (for draft win rates)
    champ_wins: dict[int, int] = {}        # champion_id -> wins
    champ_games: dict[int, int] = {}       # champion_id -> games played

    rows: list[dict] = []

    for m in matches:
        mid = m["Id"]
        blue = m["BlueTeamId"]
        red = m["RedTeamId"]
        winner = m["WinnerId"]
        duration = m["GameDuration"]

        # Initialise accumulators for unseen teams
        for tid in (blue, red):
            elo.setdefault(tid, DEFAULT_ELO)
            fb_hist.setdefault(tid, [])
            fd_hist.setdefault(tid, [])
            kills_hist.setdefault(tid, [])
            dur_hist.setdefault(tid, [])
            ft_hist.setdefault(tid, [])
            dragons_hist.setdefault(tid, [])
            towers_hist.setdefault(tid, [])
            gold_hist.setdefault(tid, [])

        # ── Compute champion win rates prior to match ───────────────────
        def _get_draft_win_rate(champs):
            if not champs:
                return 0.50
            wrs = []
            for cid in champs:
                g = champ_games.get(cid, 0)
                w = champ_wins.get(cid, 0)
                wrs.append(w / g if g > 0 else 0.50)
            return sum(wrs) / len(wrs)

        blue_champs = picks_map.get(mid, {}).get(blue, [])
        red_champs = picks_map.get(mid, {}).get(red, [])

        blue_draft_wr = _get_draft_win_rate(blue_champs)
        red_draft_wr = _get_draft_win_rate(red_champs)

        # ── Snapshot *pre-match* features ─────────────────────────────────
        def _safe_mean(lst: list, default: float = 0.0) -> float:
            return sum(lst) / len(lst) if lst else default

        row = {
            "MatchId": mid,
            "BlueTeamId": blue,
            "RedTeamId": red,
            # -- Elo --
            "Blue_Elo": elo[blue],
            "Red_Elo": elo[red],
            # -- Objective control --
            "Blue_ObjCtrl": (
                _safe_mean(fb_hist[blue], 0.5)
                + _safe_mean(fd_hist[blue], 0.5)
                + _safe_mean(ft_hist[blue], 0.5)
            ) / 3.0,
            "Red_ObjCtrl": (
                _safe_mean(fb_hist[red], 0.5)
                + _safe_mean(fd_hist[red], 0.5)
                + _safe_mean(ft_hist[red], 0.5)
            ) / 3.0,
            # -- Average kills --
            "Blue_AvgKills": _safe_mean(kills_hist[blue], 15.0),
            "Red_AvgKills": _safe_mean(kills_hist[red], 15.0),
            # -- Average game duration --
            "Blue_AvgDuration": _safe_mean(dur_hist[blue], 1800.0),
            "Red_AvgDuration": _safe_mean(dur_hist[red], 1800.0),
            # -- Avg dragons per game --
            "Blue_AvgDragons": _safe_mean(dragons_hist[blue], 2.0),
            "Red_AvgDragons": _safe_mean(dragons_hist[red], 2.0),
            # -- Avg towers per game --
            "Blue_AvgTowers": _safe_mean(towers_hist[blue], 5.0),
            "Red_AvgTowers": _safe_mean(towers_hist[red], 5.0),
            # -- Avg total gold per game --
            "Blue_AvgGold": _safe_mean(gold_hist[blue], 50000.0),
            "Red_AvgGold": _safe_mean(gold_hist[red], 50000.0),
            # -- Draft Win Rate --
            "Blue_DraftWinRate": blue_draft_wr,
            "Red_DraftWinRate": red_draft_wr,
            # -- Target --
            "BlueTeamWin": 1 if winner == blue else 0,
        }
        rows.append(row)

        # ── Update accumulators *after* recording pre-match snapshot ──────
        blue_won = winner == blue
        elo[blue], elo[red] = _update_elo(elo[blue], elo[red], blue_won)

        # Update per-team stats from MatchDetail
        for tid in (blue, red):
            d = detail_map.get(mid, {}).get(tid)
            if d:
                fb_hist[tid].append(d["FirstBlood"])
                fd_hist[tid].append(d["FirstDragon"])
                kills_hist[tid].append(d["TotalKills"])
                ft_hist[tid].append(d.get("FirstTower", 0))
                dragons_hist[tid].append(d.get("Dragons", 0))
                towers_hist[tid].append(d.get("Towers", 0))
                gold_hist[tid].append(d.get("TotalGold", 0))
            dur_hist[tid].append(duration)

        # Update rolling champion win rates
        for cid in blue_champs:
            champ_games[cid] = champ_games.get(cid, 0) + 1
            if blue_won:
                champ_wins[cid] = champ_wins.get(cid, 0) + 1
        for cid in red_champs:
            champ_games[cid] = champ_games.get(cid, 0) + 1
            if not blue_won:
                champ_wins[cid] = champ_wins.get(cid, 0) + 1

    df = pd.DataFrame(rows)
    print(f"OK: Built feature matrix: {df.shape[0]} rows x {df.shape[1]} columns (filter={league_filter})")
    return df


# ── Exporter for the latest team features ────────────────────────────────────
def get_latest_team_stats(db_path: str = DB_PATH, league_filter: str | None = None) -> tuple[dict, dict]:
    """
    Run the chronological loop to compute the final, current state of Elo and 
    rolling statistics for all teams.

    Returns
    -------
    latest_stats : dict
        team_id -> dict of latest features (Elo, ObjCtrl, AvgKills, etc.)
    team_name_to_id : dict
        normalized_team_name -> team_id
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Fetch names to build mapping
    teams = conn.execute("SELECT Id, Name FROM Team").fetchall()
    team_name_to_id = {}
    for t in teams:
        norm_name = t["Name"].strip().upper()
        team_name_to_id[norm_name] = t["Id"]

    # ── Load matches ordered chronologically ──────────────────────────────
    if league_filter:
        matches = conn.execute(
            """SELECT m.Id, m.Date, m.BlueTeamId, m.RedTeamId, m.WinnerId,
                      m.GameDuration
               FROM Match m
               WHERE m.Tournament LIKE ?
               ORDER BY m.Date, m.Id""",
            (f"{league_filter}%",)
        ).fetchall()
    else:
        matches = conn.execute(
            """SELECT m.Id, m.Date, m.BlueTeamId, m.RedTeamId, m.WinnerId,
                      m.GameDuration
               FROM Match m
               ORDER BY m.Date, m.Id"""
        ).fetchall()

    # ── Load all MatchDetail rows into a lookup ───────────────────────────
    details = conn.execute(
        "SELECT MatchId, TeamId, TotalKills, FirstBlood, FirstDragon, FirstTower, Dragons, Towers, TotalGold "
        "FROM MatchDetail"
    ).fetchall()
    
    detail_map: dict[int, dict[int, dict]] = {}
    for d in details:
        mid = d["MatchId"]
        tid = d["TeamId"]
        detail_map.setdefault(mid, {})[tid] = {
            "TotalKills": d["TotalKills"],
            "FirstBlood": d["FirstBlood"],
            "FirstDragon": d["FirstDragon"],
            "FirstTower": d["FirstTower"],
            "Dragons": d["Dragons"],
            "Towers": d["Towers"],
            "TotalGold": d["TotalGold"],
        }

    conn.close()

    # ── Accumulators per team ─────────────────────────────────────────────
    elo: dict[int, float] = {}             # team_id → current Elo
    fb_hist: dict[int, list[int]] = {}     # team_id → [0/1]
    fd_hist: dict[int, list[int]] = {}     # team_id → [0/1]
    kills_hist: dict[int, list[int]] = {}  # team_id → [total_kills]
    dur_hist: dict[int, list[int]] = {}    # team_id → [game_duration_s]
    ft_hist: dict[int, list[int]] = {}     # team_id -> [0/1] first tower
    dragons_hist: dict[int, list[int]] = {} # team_id -> [dragons per game]
    towers_hist: dict[int, list[int]] = {}  # team_id -> [towers per game]
    gold_hist: dict[int, list[int]] = {}    # team_id -> [total gold per game]

    for m in matches:
        mid = m["Id"]
        blue = m["BlueTeamId"]
        red = m["RedTeamId"]
        winner = m["WinnerId"]
        duration = m["GameDuration"]

        # Initialise accumulators for unseen teams
        for tid in (blue, red):
            elo.setdefault(tid, DEFAULT_ELO)
            fb_hist.setdefault(tid, [])
            fd_hist.setdefault(tid, [])
            kills_hist.setdefault(tid, [])
            dur_hist.setdefault(tid, [])
            ft_hist.setdefault(tid, [])
            dragons_hist.setdefault(tid, [])
            towers_hist.setdefault(tid, [])
            gold_hist.setdefault(tid, [])

        blue_won = winner == blue
        elo[blue], elo[red] = _update_elo(elo[blue], elo[red], blue_won)

        for tid in (blue, red):
            d = detail_map.get(mid, {}).get(tid)
            if d:
                fb_hist[tid].append(d["FirstBlood"])
                fd_hist[tid].append(d["FirstDragon"])
                kills_hist[tid].append(d["TotalKills"])
                ft_hist[tid].append(d.get("FirstTower", 0))
                dragons_hist[tid].append(d.get("Dragons", 0))
                towers_hist[tid].append(d.get("Towers", 0))
                gold_hist[tid].append(d.get("TotalGold", 0))
            dur_hist[tid].append(duration)

    # ── Compile latest features dict ──────────────────────────────────────────
    def _safe_mean(lst: list, default: float = 0.0) -> float:
        return sum(lst) / len(lst) if lst else default

    latest_stats = {}
    for tid in elo.keys():
        latest_stats[tid] = {
            "Elo": elo[tid],
            "ObjCtrl": (
                _safe_mean(fb_hist[tid], 0.5)
                + _safe_mean(fd_hist[tid], 0.5)
                + _safe_mean(ft_hist[tid], 0.5)
            ) / 3.0,
            "AvgKills": _safe_mean(kills_hist[tid], 15.0),
            "AvgDuration": _safe_mean(dur_hist[tid], 1800.0),
            "AvgDragons": _safe_mean(dragons_hist[tid], 2.0),
            "AvgTowers": _safe_mean(towers_hist[tid], 5.0),
            "AvgGold": _safe_mean(gold_hist[tid], 50000.0),
        }

    return latest_stats, team_name_to_id


# ── Convenience: feature column names ────────────────────────────────────────
FEATURE_COLS = [
    "Blue_Elo",
    "Red_Elo",
    "Blue_ObjCtrl",
    "Red_ObjCtrl",
    "Blue_AvgKills",
    "Red_AvgKills",
    "Blue_AvgDuration",
    "Red_AvgDuration",
    "Blue_AvgDragons",
    "Red_AvgDragons",
    "Blue_AvgTowers",
    "Red_AvgTowers",
    "Blue_AvgGold",
    "Red_AvgGold",
    "Blue_DraftWinRate",
    "Red_DraftWinRate",
]

TARGET_COL = "BlueTeamWin"

if __name__ == "__main__":
    df = build_feature_dataframe()
    print("DataFrame columns:", list(df.columns))
    print(df.head(5).to_string(index=False))
