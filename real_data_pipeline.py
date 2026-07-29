"""
real_data_pipeline.py — Import real LPL match data from Oracle's Elixir CSV
into the existing SQLite schema.

Supports two data sources:
  1. Oracle's Elixir CSV (primary — recommended)
  2. Leaguepedia Cargo API (secondary — programmatic)

Usage:
  python real_data_pipeline.py --csv "path/to/2025_LoL_esports_match_data_from_OraclesElixir.csv"
  python real_data_pipeline.py --csv "path/to/data.csv" --league LPL
  python real_data_pipeline.py --leaguepedia --tournament "LPL 2025 Split 1"

Strictly synchronous — no asyncio/aiohttp.
"""

import argparse
import csv
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict

import requests

# ── Configuration ────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "lpl_prediction.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def init_database(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Create/open the database and apply the schema (idempotent)."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn


# =============================================================================
#  SOURCE 1: Oracle's Elixir CSV
# =============================================================================
#
#  The CSV has one row per player per game, PLUS one row per team per game
#  (where position = "team"). Key columns:
#
#  gameid, league, year, split, playoffs, date, game, patch, side,
#  position, playername, teamname, champion, result (1=win, 0=loss),
#  kills, deaths, assists, teamkills, teamdeaths,
#  firstblood, firstdragon, firstherald, firstbaron, firsttower,
#  golddiffat15, damagetochampions, visionscore, totalgold,
#  minionkills, monsterkills, gamelength (seconds)
# =============================================================================

def _get_or_create(
    cur: sqlite3.Cursor, table: str, name: str, extras: dict | None = None
) -> int:
    """Get Id for a named entity, inserting if it doesn't exist."""
    cur.execute(f"SELECT Id FROM {table} WHERE Name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]

    cols = ["Name"] + list((extras or {}).keys())
    vals = [name] + list((extras or {}).values())
    placeholders = ", ".join(["?"] * len(vals))
    col_str = ", ".join(cols)
    cur.execute(f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})", vals)
    return cur.lastrowid


def _safe_int(val, default: int = 0) -> int:
    """Convert a CSV value to int, handling empty strings and floats."""
    if val is None or val == "":
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_float(val, default: float = 0.0) -> float:
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _normalize_role(position: str) -> str:
    """Map Oracle's Elixir position names to our schema's Role values."""
    mapping = {
        "top": "Top",
        "jng": "Jungle",
        "jungle": "Jungle",
        "mid": "Mid",
        "bot": "Bot",
        "adc": "Bot",
        "sup": "Support",
        "support": "Support",
    }
    return mapping.get(position.lower().strip(), position.capitalize())


def import_oracle_csv(
    csv_path: str,
    db_path: str = DB_PATH,
    league_filter: str | None = None,
) -> None:
    """
    Parse an Oracle's Elixir CSV and populate the LPL prediction database.

    Parameters
    ----------
    csv_path : str
        Path to the downloaded CSV file.
    db_path : str
        Path to the SQLite database.
    league_filter : str, optional
        If provided, only import rows where the 'league' column matches
        (e.g., "LPL", "LCK", "LEC"). Case-insensitive.
    """
    if not os.path.isfile(csv_path):
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    conn = init_database(db_path)
    cur = conn.cursor()

    # ── Pass 1: Read and group rows by gameid ─────────────────────────────
    print(f"Reading CSV: {csv_path} ...")
    games: dict[str, list[dict]] = defaultdict(list)
    total_rows = 0

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1
            # Apply league filter if requested
            if league_filter:
                row_league = (row.get("league") or "").strip()
                if row_league.upper() != league_filter.upper():
                    continue
            gid = row.get("gameid", "")
            if gid:
                games[gid].append(row)

    print(f"  Total CSV rows: {total_rows}")
    print(f"  Games after filter: {len(games)}")

    if not games:
        print("WARNING: No games found. Check your --league filter.")
        conn.close()
        return

    # ── Pass 2: Process each game chronologically ─────────────────────────
    # Sort games by date
    def _game_date(rows):
        for r in rows:
            d = r.get("date", "")
            if d:
                return d
        return "9999-12-31"

    sorted_game_ids = sorted(games.keys(), key=lambda gid: _game_date(games[gid]))

    inserted = 0
    skipped = 0

    try:
        from tqdm import tqdm
        game_iter = tqdm(sorted_game_ids, desc="Importing matches")
    except ImportError:
        game_iter = sorted_game_ids

    for gid in game_iter:
        rows = games[gid]

        # Separate team-level rows from player-level rows
        team_rows = [r for r in rows if (r.get("position") or "").lower() == "team"]
        player_rows = [r for r in rows if (r.get("position") or "").lower() != "team"]

        if len(team_rows) != 2:
            # Need exactly 2 team rows (blue + red)
            skipped += 1
            continue

        # Identify blue and red team rows
        blue_team_row = None
        red_team_row = None
        for tr in team_rows:
            side = (tr.get("side") or "").strip().capitalize()
            if side == "Blue":
                blue_team_row = tr
            elif side == "Red":
                red_team_row = tr

        if not blue_team_row or not red_team_row:
            skipped += 1
            continue

        # ── Extract match-level info ──────────────────────────────────────
        blue_name = (blue_team_row.get("teamname") or "Unknown").strip()
        red_name = (red_team_row.get("teamname") or "Unknown").strip()
        date_str = (blue_team_row.get("date") or "2024-01-01").strip()[:10]
        patch = (blue_team_row.get("patch") or "").strip()
        duration = _safe_int(blue_team_row.get("gamelength"), 1800)

        # Tournament: combine league + year + split
        league = (blue_team_row.get("league") or "LPL").strip()
        year = (blue_team_row.get("year") or "").strip()
        split = (blue_team_row.get("split") or "").strip()
        playoffs = (blue_team_row.get("playoffs") or "0").strip()
        tournament = f"{league} {year} {split}"
        if playoffs == "1":
            tournament += " Playoffs"
        tournament = tournament.strip()

        # Winner
        blue_result = _safe_int(blue_team_row.get("result"), 0)

        # ── Upsert teams ─────────────────────────────────────────────────
        blue_team_id = _get_or_create(cur, "Team", blue_name, {"Region": league})
        red_team_id = _get_or_create(cur, "Team", red_name, {"Region": league})
        winner_id = blue_team_id if blue_result == 1 else red_team_id

        # ── Insert Match ──────────────────────────────────────────────────
        cur.execute(
            """INSERT INTO Match
               (Tournament, Date, Patch, BlueTeamId, RedTeamId, WinnerId, GameDuration)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tournament, date_str, patch, blue_team_id, red_team_id, winner_id, duration),
        )
        match_id = cur.lastrowid

        # ── Insert MatchDetail (one per side) ─────────────────────────────
        for side_label, team_id, tr in [
            ("Blue", blue_team_id, blue_team_row),
            ("Red", red_team_id, red_team_row),
        ]:
            total_kills = _safe_int(tr.get("teamkills") or tr.get("kills"), 0)
            total_deaths = _safe_int(tr.get("teamdeaths") or tr.get("deaths"), 0)
            gd15 = _safe_int(tr.get("golddiffat15"), 0)
            fb = _safe_int(tr.get("firstblood"), 0)
            fd = _safe_int(tr.get("firstdragon"), 0)
            ft = _safe_int(tr.get("firsttower"), 0)
            dragons = _safe_int(tr.get("dragons"), 0)
            heralds = _safe_int(tr.get("heralds"), 0)
            barons = _safe_int(tr.get("barons"), 0)
            towers = _safe_int(tr.get("towers"), 0)
            total_gold = _safe_int(tr.get("totalgold"), 0)

            cur.execute(
                """INSERT INTO MatchDetail
                   (MatchId, TeamId, Side, TotalKills, TotalDeaths,
                    GoldDiff15, FirstBlood, FirstDragon,
                    FirstTower, Dragons, Heralds, Barons, Towers, TotalGold)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (match_id, team_id, side_label, total_kills, total_deaths,
                 gd15, fb, fd, ft, dragons, heralds, barons, towers, total_gold),
            )

        # ── Insert PlayerStat (one per player) ───────────────────────────
        for pr in player_rows:
            position = (pr.get("position") or "").strip()
            if not position or position.lower() == "team":
                continue

            player_name = (pr.get("playername") or "Unknown").strip()
            champ_name = (pr.get("champion") or "Unknown").strip()
            side = (pr.get("side") or "").strip().capitalize()
            team_name = (pr.get("teamname") or "Unknown").strip()

            team_id = _get_or_create(cur, "Team", team_name, {"Region": league})
            player_id = _get_or_create(
                cur, "Player", player_name,
                {"TeamId": team_id, "Role": _normalize_role(position)}
            )
            champ_id = _get_or_create(cur, "Champion", champ_name, {"PrimaryRole": ""})

            role = _normalize_role(position)
            kills = _safe_int(pr.get("kills"), 0)
            deaths = _safe_int(pr.get("deaths"), 0)
            assists = _safe_int(pr.get("assists"), 0)
            cs = _safe_int(pr.get("minionkills"), 0) + _safe_int(pr.get("monsterkills"), 0)
            damage = _safe_int(pr.get("damagetochampions"), 0)
            vision = _safe_int(pr.get("visionscore"), 0)

            cur.execute(
                """INSERT INTO PlayerStat
                   (MatchId, PlayerId, ChampionId, Role,
                    Kills, Deaths, Assists, CS, DamageDealt, VisionScore)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (match_id, player_id, champ_id, role,
                 kills, deaths, assists, cs, damage, vision),
            )

        # ── Insert PickBan ────────────────────────────────────────────────
        # Oracle's Elixir doesn't always have full draft data in the CSV;
        # we can extract picked champions from player rows.
        # Bans are in columns ban1–ban5 on team rows (if available).
        order_counter = 1

        # Bans (from team rows, columns ban1..ban5)
        for side_label, team_id, tr in [
            ("Blue", blue_team_id, blue_team_row),
            ("Red", red_team_id, red_team_row),
        ]:
            for ban_col in ["ban1", "ban2", "ban3", "ban4", "ban5"]:
                ban_champ = (tr.get(ban_col) or "").strip()
                if ban_champ:
                    ban_champ_id = _get_or_create(
                        cur, "Champion", ban_champ, {"PrimaryRole": ""}
                    )
                    phase = 1 if ban_col in ("ban1", "ban2", "ban3") else 2
                    cur.execute(
                        """INSERT INTO PickBan
                           (MatchId, TeamId, ChampionId, IsBan, Phase, "Order")
                           VALUES (?, ?, ?, 1, ?, ?)""",
                        (match_id, team_id, ban_champ_id, phase, order_counter),
                    )
                    order_counter += 1

        # Picks (from player rows)
        for pr in player_rows:
            champ_name = (pr.get("champion") or "").strip()
            team_name = (pr.get("teamname") or "Unknown").strip()
            if not champ_name:
                continue
            team_id = _get_or_create(cur, "Team", team_name, {"Region": league})
            champ_id = _get_or_create(cur, "Champion", champ_name, {"PrimaryRole": ""})
            cur.execute(
                """INSERT INTO PickBan
                   (MatchId, TeamId, ChampionId, IsBan, Phase, "Order")
                   VALUES (?, ?, ?, 0, 1, ?)""",
                (match_id, team_id, champ_id, order_counter),
            )
            order_counter += 1

        inserted += 1
        if inserted % 50 == 0:
            conn.commit()

    conn.commit()
    conn.close()

    print(f"\n  Imported: {inserted} games")
    print(f"  Skipped:  {skipped} games (incomplete data)")
    print(f"  Database: {db_path}")


# =============================================================================
#  SOURCE 2: Leaguepedia Cargo API
# =============================================================================

LEAGUEPEDIA_API = "https://lol.fandom.com/api.php"
REQUEST_DELAY = 1.0  # seconds between requests (be polite)


def _cargo_query(tables: str, fields: str, where: str, limit: int = 500) -> list[dict]:
    """Execute a single Cargo API query and return list of result dicts."""
    results = []
    offset = 0

    while True:
        params = {
            "action": "cargoquery",
            "format": "json",
            "tables": tables,
            "fields": fields,
            "where": where,
            "limit": str(min(limit, 500)),
            "offset": str(offset),
        }
        print(f"  API request: offset={offset} ...")
        resp = requests.get(LEAGUEPEDIA_API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("cargoquery", [])
        if not batch:
            break
        results.extend([item["title"] for item in batch])
        if len(batch) < 500:
            break
        offset += 500
        time.sleep(REQUEST_DELAY)

    return results


def import_leaguepedia(
    tournament: str,
    db_path: str = DB_PATH,
) -> None:
    """
    Fetch match data from Leaguepedia's Cargo API for a given tournament
    and populate the database.

    Parameters
    ----------
    tournament : str
        Exact Leaguepedia tournament name, e.g. "LPL 2025 Split 1".
    db_path : str
        Path to the SQLite database.
    """
    conn = init_database(db_path)
    cur = conn.cursor()

    print(f"\nFetching games for tournament: {tournament}")

    # ── Step 1: Get game-level data from ScoreboardGames ──────────────────
    game_fields = (
        "GameId, DateTime_UTC, Patch, Team1, Team2, Winner, "
        "Team1Bans, Team2Bans, Team1Picks, Team2Picks, "
        "Team1Gold, Team2Gold, Gamelength, "
        "Team1Kills, Team2Kills, Team1Deaths, Team2Deaths, "
        "Team1Dragons, Team2Dragons"
    )
    game_where = f'Tournament="{tournament}"'
    game_rows = _cargo_query("ScoreboardGames", game_fields, game_where)

    if not game_rows:
        print(f"  No games found for tournament '{tournament}'.")
        print("  Tip: Check exact tournament names at https://lol.fandom.com/wiki/Special:CargoTables")
        conn.close()
        return

    print(f"  Found {len(game_rows)} games.")

    # ── Step 2: Get player stats from ScoreboardPlayers ───────────────────
    player_fields = (
        "GameId, Name, Team, Champion, Role, "
        "Kills, Deaths, Assists, CS, DamageToChampions, VisionScore"
    )
    player_where = f'OverviewPage="{tournament}"'
    player_rows = _cargo_query("ScoreboardPlayers", player_fields, player_where)

    # Index player rows by GameId
    players_by_game: dict[str, list[dict]] = defaultdict(list)
    for pr in player_rows:
        gid = pr.get("GameId", "")
        if gid:
            players_by_game[gid].append(pr)

    print(f"  Found {len(player_rows)} player stat rows.")

    # ── Step 3: Insert into database ──────────────────────────────────────
    inserted = 0
    for gr in sorted(game_rows, key=lambda x: x.get("DateTime UTC", "")):
        game_id = gr.get("GameId", "")
        date_str = (gr.get("DateTime UTC") or "2024-01-01")[:10]
        patch = (gr.get("Patch") or "").strip()

        team1_name = (gr.get("Team1") or "Unknown").strip()
        team2_name = (gr.get("Team2") or "Unknown").strip()
        winner_name = (gr.get("Winner") or "").strip()

        # Parse game length (format: "mm:ss" or seconds)
        gl_raw = (gr.get("Gamelength") or "30:00").strip()
        if ":" in gl_raw:
            parts = gl_raw.split(":")
            duration = int(parts[0]) * 60 + int(parts[1])
        else:
            duration = _safe_int(gl_raw, 1800)

        # Teams (Team1 = Blue side, Team2 = Red side in Leaguepedia)
        blue_id = _get_or_create(cur, "Team", team1_name, {"Region": "LPL"})
        red_id = _get_or_create(cur, "Team", team2_name, {"Region": "LPL"})
        winner_id = blue_id if winner_name == team1_name else red_id

        cur.execute(
            """INSERT INTO Match
               (Tournament, Date, Patch, BlueTeamId, RedTeamId, WinnerId, GameDuration)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tournament, date_str, patch, blue_id, red_id, winner_id, duration),
        )
        match_id = cur.lastrowid

        # MatchDetail
        for side, tid, tr, opp_tr in [
            ("Blue", blue_id, gr, gr),
            ("Red", red_id, gr, gr),
        ]:
            prefix = "Team1" if side == "Blue" else "Team2"
            opp_prefix = "Team2" if side == "Blue" else "Team1"
            kills = _safe_int(tr.get(f"{prefix}Kills"), 0)
            deaths = _safe_int(tr.get(f"{prefix}Deaths"), 0)

            cur.execute(
                """INSERT INTO MatchDetail
                   (MatchId, TeamId, Side, TotalKills, TotalDeaths,
                    GoldDiff15, FirstBlood, FirstDragon)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (match_id, tid, side, kills, deaths, 0, 0, 0),
            )

        # PickBan (bans from comma-separated fields)
        order_counter = 1
        for side, tid, prefix in [("Blue", blue_id, "Team1"), ("Red", red_id, "Team2")]:
            bans_str = (gr.get(f"{prefix}Bans") or "").strip()
            if bans_str:
                for ban_name in bans_str.split(","):
                    ban_name = ban_name.strip()
                    if ban_name:
                        cid = _get_or_create(cur, "Champion", ban_name, {"PrimaryRole": ""})
                        cur.execute(
                            """INSERT INTO PickBan
                               (MatchId, TeamId, ChampionId, IsBan, Phase, "Order")
                               VALUES (?, ?, ?, 1, 1, ?)""",
                            (match_id, tid, cid, order_counter),
                        )
                        order_counter += 1

            picks_str = (gr.get(f"{prefix}Picks") or "").strip()
            if picks_str:
                for pick_name in picks_str.split(","):
                    pick_name = pick_name.strip()
                    if pick_name:
                        cid = _get_or_create(cur, "Champion", pick_name, {"PrimaryRole": ""})
                        cur.execute(
                            """INSERT INTO PickBan
                               (MatchId, TeamId, ChampionId, IsBan, Phase, "Order")
                               VALUES (?, ?, ?, 0, 1, ?)""",
                            (match_id, tid, cid, order_counter),
                        )
                        order_counter += 1

        # PlayerStat
        for pr in players_by_game.get(game_id, []):
            p_name = (pr.get("Name") or "Unknown").strip()
            p_team = (pr.get("Team") or "Unknown").strip()
            p_champ = (pr.get("Champion") or "Unknown").strip()
            p_role = _normalize_role(pr.get("Role") or "")

            p_team_id = _get_or_create(cur, "Team", p_team, {"Region": "LPL"})
            p_player_id = _get_or_create(
                cur, "Player", p_name,
                {"TeamId": p_team_id, "Role": p_role},
            )
            p_champ_id = _get_or_create(cur, "Champion", p_champ, {"PrimaryRole": ""})

            cur.execute(
                """INSERT INTO PlayerStat
                   (MatchId, PlayerId, ChampionId, Role,
                    Kills, Deaths, Assists, CS, DamageDealt, VisionScore)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    match_id,
                    p_player_id,
                    p_champ_id,
                    p_role,
                    _safe_int(pr.get("Kills")),
                    _safe_int(pr.get("Deaths")),
                    _safe_int(pr.get("Assists")),
                    _safe_int(pr.get("CS")),
                    _safe_int(pr.get("DamageToChampions")),
                    _safe_int(pr.get("VisionScore")),
                ),
            )

        inserted += 1
        if inserted % 20 == 0:
            conn.commit()
            print(f"  ... processed {inserted} games")

        time.sleep(0.1)  # small delay to avoid overloading

    conn.commit()
    conn.close()
    print(f"\n  Imported {inserted} games from Leaguepedia.")
    print(f"  Database: {db_path}")


# =============================================================================
#  CLI Entry Point
# =============================================================================

def crawl_completed_match(blue_team_name: str, red_team_name: str, date_str: str, db_path: str = DB_PATH) -> int:
    """
    Query Leaguepedia Cargo API for a completed match on a specific date,
    and insert its game details and player stats into the database.
    """
    # Normalize inputs
    blue = blue_team_name.strip()
    red = red_team_name.strip()
    date_val = date_str[:10]  # YYYY-MM-DD
    
    conn = init_database(db_path)
    cur = conn.cursor()
    
    # Check if match already exists in database
    blue_id_row = cur.execute("SELECT Id FROM Team WHERE Name = ?", (blue,)).fetchone()
    red_id_row = cur.execute("SELECT Id FROM Team WHERE Name = ?", (red,)).fetchone()
    
    if blue_id_row and red_id_row:
        b_id = blue_id_row[0]
        r_id = red_id_row[0]
        exists = cur.execute(
            """SELECT 1 FROM Match 
               WHERE ((BlueTeamId = ? AND RedTeamId = ?) OR (BlueTeamId = ? AND RedTeamId = ?)) 
                 AND Date = ?""",
            (b_id, r_id, r_id, b_id, date_val)
        ).fetchone()
        if exists:
            conn.close()
            return 0  # Already imported
            
    print(f"[AUTO-CRAWL] Fetching completed game data from Leaguepedia: {blue} vs {red} on {date_val}...")
    
    # Query game-level data
    game_fields = (
        "GameId, DateTime_UTC, Patch, Team1, Team2, Winner, "
        "Team1Bans, Team2Bans, Team1Picks, Team2Picks, "
        "Team1Gold, Team2Gold, Gamelength, "
        "Team1Kills, Team2Kills, Team1Deaths, Team2Deaths, "
        "Team1Dragons, Team2Dragons"
    )
    where = (
        f"((Team1 = '{blue}' AND Team2 = '{red}') OR "
        f"(Team1 = '{red}' AND Team2 = '{blue}')) AND "
        f"DateTime_UTC LIKE '{date_val}%'"
    )
    
    try:
        game_rows = _cargo_query("ScoreboardGames", game_fields, where)
    except Exception as e:
        print(f"[AUTO-CRAWL] API Error fetching games: {e}")
        conn.close()
        return 0
        
    if not game_rows:
        print(f"[AUTO-CRAWL] No games found on Leaguepedia for {blue} vs {red} on {date_val}.")
        conn.close()
        return 0
        
    print(f"[AUTO-CRAWL] Found {len(game_rows)} games. Fetching player stats...")
    
    # Query player-level stats
    game_ids = [gr["GameId"] for gr in game_rows]
    game_ids_str = ", ".join([f"'{gid}'" for gid in game_ids])
    
    player_fields = (
        "GameId, Name, Team, Champion, Role, "
        "Kills, Deaths, Assists, CS, DamageToChampions, VisionScore"
    )
    player_where = f"GameId IN ({game_ids_str})"
    
    try:
        player_rows = _cargo_query("ScoreboardPlayers", player_fields, player_where)
    except Exception as e:
        print(f"[AUTO-CRAWL] API Error fetching player stats: {e}")
        conn.close()
        return 0
        
    # Index player rows by GameId
    players_by_game = defaultdict(list)
    for pr in player_rows:
        gid = pr.get("GameId", "")
        if gid:
            players_by_game[gid].append(pr)
            
    inserted = 0
    # Insert games into database
    for gr in sorted(game_rows, key=lambda x: x.get("DateTime UTC", "")):
        game_id = gr.get("GameId", "")
        patch = (gr.get("Patch") or "").strip()
        winner_name = (gr.get("Winner") or "").strip()
        
        gl_raw = (gr.get("Gamelength") or "30:00").strip()
        if ":" in gl_raw:
            parts = gl_raw.split(":")
            duration = int(parts[0]) * 60 + int(parts[1])
        else:
            duration = _safe_int(gl_raw, 1800)
            
        b_id = _get_or_create(cur, "Team", gr.get("Team1", blue), {"Region": "LPL"})
        r_id = _get_or_create(cur, "Team", gr.get("Team2", red), {"Region": "LPL"})
        w_id = b_id if winner_name == gr.get("Team1") else r_id
        
        cur.execute(
            """INSERT INTO Match
               (Tournament, Date, Patch, BlueTeamId, RedTeamId, WinnerId, GameDuration)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("LPL 2025 Split 1", date_val, patch, b_id, r_id, w_id, duration)
        )
        match_id = cur.lastrowid
        
        # MatchDetail
        for side, tid, tr in [("Blue", b_id, gr), ("Red", r_id, gr)]:
            prefix = "Team1" if side == "Blue" else "Team2"
            kills = _safe_int(tr.get(f"{prefix}Kills"), 0)
            deaths = _safe_int(tr.get(f"{prefix}Deaths"), 0)
            
            cur.execute(
                """INSERT INTO MatchDetail
                   (MatchId, TeamId, Side, TotalKills, TotalDeaths,
                    GoldDiff15, FirstBlood, FirstDragon)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (match_id, tid, side, kills, deaths, 0, 0, 0)
            )
            
        # PickBan
        order_counter = 1
        for side, tid, prefix in [("Blue", b_id, "Team1"), ("Red", r_id, "Team2")]:
            bans_str = (gr.get(f"{prefix}Bans") or "").strip()
            if bans_str:
                for ban_name in bans_str.split(","):
                    ban_name = ban_name.strip()
                    if ban_name:
                        cid = _get_or_create(cur, "Champion", ban_name, {"PrimaryRole": ""})
                        cur.execute(
                            """INSERT INTO PickBan
                               (MatchId, TeamId, ChampionId, IsBan, Phase, "Order")
                               VALUES (?, ?, ?, 1, 1, ?)""",
                            (match_id, tid, cid, order_counter)
                        )
                        order_counter += 1
                        
            picks_str = (gr.get(f"{prefix}Picks") or "").strip()
            if picks_str:
                for pick_name in picks_str.split(","):
                    pick_name = pick_name.strip()
                    if pick_name:
                        cid = _get_or_create(cur, "Champion", pick_name, {"PrimaryRole": ""})
                        cur.execute(
                            """INSERT INTO PickBan
                               (MatchId, TeamId, ChampionId, IsBan, Phase, "Order")
                               VALUES (?, ?, ?, 0, 1, ?)""",
                            (match_id, tid, cid, order_counter)
                        )
                        order_counter += 1
                        
        # PlayerStat
        for pr in players_by_game.get(game_id, []):
            p_name = (pr.get("Name") or "Unknown").strip()
            p_team = (pr.get("Team") or "Unknown").strip()
            p_champ = (pr.get("Champion") or "Unknown").strip()
            p_role = _normalize_role(pr.get("Role") or "")
            
            p_team_id = _get_or_create(cur, "Team", p_team, {"Region": "LPL"})
            p_player_id = _get_or_create(
                cur, "Player", p_name,
                {"TeamId": p_team_id, "Role": p_role}
            )
            p_champ_id = _get_or_create(cur, "Champion", p_champ, {"PrimaryRole": ""})
            
            cur.execute(
                """INSERT INTO PlayerStat
                   (MatchId, PlayerId, ChampionId, Role,
                    Kills, Deaths, Assists, CS, DamageDealt, VisionScore)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (match_id, p_player_id, p_champ_id, p_role,
                 _safe_int(pr.get("Kills")), _safe_int(pr.get("Deaths")), _safe_int(pr.get("Assists")),
                 _safe_int(pr.get("CS")), _safe_int(pr.get("DamageToChampions")), _safe_int(pr.get("VisionScore")))
            )
            
        inserted += 1
        
    conn.commit()
    conn.close()
    print(f"[AUTO-CRAWL] Successfully imported {inserted} games into the database.")
    return inserted


def main():
    parser = argparse.ArgumentParser(
        description="Import real LoL esports data into the prediction database."
    )
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Path to Oracle's Elixir CSV file."
    )
    parser.add_argument(
        "--league", type=str, default=None,
        help="Filter CSV by league (e.g., LPL, LCK, LEC). Only used with --csv."
    )
    parser.add_argument(
        "--leaguepedia", action="store_true",
        help="Fetch data from Leaguepedia Cargo API instead."
    )
    parser.add_argument(
        "--tournament", type=str, default="LPL 2025 Split 1",
        help="Leaguepedia tournament name. Only used with --leaguepedia."
    )
    parser.add_argument(
        "--db", type=str, default=DB_PATH,
        help=f"Path to SQLite database (default: {DB_PATH})."
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="Delete existing database and start fresh."
    )
    args = parser.parse_args()

    # Optionally start fresh
    if args.fresh and os.path.exists(args.db):
        os.remove(args.db)
        print(f"Deleted existing database: {args.db}")

    if args.csv:
        import_oracle_csv(args.csv, db_path=args.db, league_filter=args.league)
    elif args.leaguepedia:
        import_leaguepedia(args.tournament, db_path=args.db)
    else:
        parser.print_help()
        print("\nExamples:")
        print('  python real_data_pipeline.py --csv "data.csv" --league LPL --fresh')
        print('  python real_data_pipeline.py --leaguepedia --tournament "LPL 2025 Split 1" --fresh')


if __name__ == "__main__":
    main()
