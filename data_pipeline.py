"""
data_pipeline.py — Synchronous data ingestion for the LPL prediction database.

Generates realistic mock data (8 LPL teams, 80 champions, 200 matches) and
inserts it into the SQLite database using strictly synchronous execution.
No asyncio / aiohttp anywhere.
"""

import sqlite3
import random
import os
from datetime import datetime, timedelta

# ── Configuration ────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "lpl_prediction.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
SEED = 42
random.seed(SEED)

# ── Reference data ───────────────────────────────────────────────────────────
LPL_TEAMS = [
    "JDG", "BLG", "TES", "WBG",
    "LNG", "EDG", "OMG", "FPX",
]

ROLES = ["Top", "Jungle", "Mid", "Bot", "Support"]

# 80 champions (real names for realism in the draft table)
CHAMPIONS = [
    ("Aatrox", "Fighter"), ("Ahri", "Mage"), ("Akali", "Assassin"),
    ("Alistar", "Tank"), ("Aphelios", "Marksman"), ("Ashe", "Marksman"),
    ("Azir", "Mage"), ("Braum", "Support"), ("Caitlyn", "Marksman"),
    ("Camille", "Fighter"), ("Corki", "Marksman"), ("Darius", "Fighter"),
    ("Diana", "Assassin"), ("Draven", "Marksman"), ("Ezreal", "Marksman"),
    ("Fiora", "Fighter"), ("Galio", "Tank"), ("Gnar", "Fighter"),
    ("Gragas", "Tank"), ("Graves", "Fighter"), ("Gwen", "Fighter"),
    ("Jayce", "Fighter"), ("Jhin", "Marksman"), ("Jinx", "Marksman"),
    ("K'Sante", "Tank"), ("Kai'Sa", "Marksman"), ("Kalista", "Marksman"),
    ("Karma", "Support"), ("Kennen", "Mage"), ("Kha'Zix", "Assassin"),
    ("Kindred", "Marksman"), ("Lee Sin", "Fighter"), ("Leona", "Tank"),
    ("Lissandra", "Mage"), ("Lucian", "Marksman"), ("Lulu", "Support"),
    ("Maokai", "Tank"), ("Miss Fortune", "Marksman"), ("Morgana", "Support"),
    ("Nami", "Support"), ("Nautilus", "Tank"), ("Nidalee", "Assassin"),
    ("Orianna", "Mage"), ("Ornn", "Tank"), ("Poppy", "Tank"),
    ("Pyke", "Assassin"), ("Rakan", "Support"), ("Rek'Sai", "Fighter"),
    ("Renata Glasc", "Support"), ("Renekton", "Fighter"), ("Rumble", "Mage"),
    ("Sejuani", "Tank"), ("Senna", "Support"), ("Sett", "Fighter"),
    ("Sivir", "Marksman"), ("Syndra", "Mage"), ("Taliyah", "Mage"),
    ("Thresh", "Support"), ("Tristana", "Marksman"), ("Trundle", "Fighter"),
    ("Twisted Fate", "Mage"), ("Varus", "Marksman"), ("Vi", "Fighter"),
    ("Viego", "Assassin"), ("Viktor", "Mage"), ("Vladimir", "Mage"),
    ("Wukong", "Fighter"), ("Xayah", "Marksman"), ("Xin Zhao", "Fighter"),
    ("Yasuo", "Fighter"), ("Yone", "Fighter"), ("Yuumi", "Support"),
    ("Zac", "Tank"), ("Zed", "Assassin"), ("Zeri", "Marksman"),
    ("Ziggs", "Mage"), ("Zilean", "Support"), ("Zyra", "Support"),
    ("Lux", "Mage"), ("Jax", "Fighter"),
]

PLAYER_NAMES = {
    "JDG": ["369", "Kanavi", "Yagao", "Ruler", "Missing"],
    "BLG": ["Bin", "Xun", "knight", "Elk", "ON"],
    "TES": ["Wayward", "Tian", "Creme", "Jackeylove", "Mark"],
    "WBG": ["TheShy", "Weiwei", "Xiaohu", "Light", "Crisp"],
    "LNG": ["Zika", "Tarzan", "Scout", "GALA", "Hang"],
    "EDG": ["Ale", "Jiejie", "FoFo", "Leave", "Meiko"],
    "OMG": ["shanji", "Aki", "Creme2", "Able", "PPgod"],
    "FPX": ["Milkyway", "Clid", "Care", "Lwx", "Lele"],
}

TOURNAMENTS = [
    "LPL 2024 Spring", "LPL 2024 Spring Playoffs",
    "LPL 2024 Summer", "LPL 2024 Summer Playoffs",
]

PATCHES = ["14.1", "14.3", "14.5", "14.7", "14.9", "14.11", "14.13"]


# ── Helper: initialise schema ────────────────────────────────────────────────
def init_database(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Create the database and apply the schema (idempotent)."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn


# ── Step 1: Seed static reference tables ─────────────────────────────────────
def seed_teams(conn: sqlite3.Connection) -> dict[str, int]:
    """Insert teams; return {name: Id} map."""
    cur = conn.cursor()
    team_map: dict[str, int] = {}
    for name in LPL_TEAMS:
        cur.execute(
            "INSERT OR IGNORE INTO Team (Name, Region) VALUES (?, 'LPL')",
            (name,),
        )
        cur.execute("SELECT Id FROM Team WHERE Name = ?", (name,))
        team_map[name] = cur.fetchone()[0]
    conn.commit()
    return team_map


def seed_champions(conn: sqlite3.Connection) -> dict[str, int]:
    """Insert champions; return {name: Id} map."""
    cur = conn.cursor()
    champ_map: dict[str, int] = {}
    for name, role in CHAMPIONS:
        cur.execute(
            "INSERT OR IGNORE INTO Champion (Name, PrimaryRole) VALUES (?, ?)",
            (name, role),
        )
        cur.execute("SELECT Id FROM Champion WHERE Name = ?", (name,))
        champ_map[name] = cur.fetchone()[0]
    conn.commit()
    return champ_map


def seed_players(
    conn: sqlite3.Connection, team_map: dict[str, int]
) -> dict[str, int]:
    """Insert players; return {ign: Id} map."""
    cur = conn.cursor()
    player_map: dict[str, int] = {}
    for team_name, roster in PLAYER_NAMES.items():
        for idx, ign in enumerate(roster):
            role = ROLES[idx]
            cur.execute(
                "INSERT OR IGNORE INTO Player (Name, TeamId, Role) VALUES (?, ?, ?)",
                (ign, team_map[team_name], role),
            )
            cur.execute("SELECT Id FROM Player WHERE Name = ?", (ign,))
            player_map[ign] = cur.fetchone()[0]
    conn.commit()
    return player_map


# ── Step 2: Generate match data (synchronous, chronological) ─────────────────
def _random_date(start: datetime, end: datetime) -> str:
    """Return a random ISO date between start and end."""
    delta = (end - start).days
    return (start + timedelta(days=random.randint(0, delta))).strftime("%Y-%m-%d")


def generate_matches(
    conn: sqlite3.Connection,
    team_map: dict[str, int],
    champ_map: dict[str, int],
    player_map: dict[str, int],
    n_matches: int = 200,
) -> None:
    """
    Generate *n_matches* synthetic matches and insert them sequentially.
    Each match creates rows in: Match, MatchDetail (×2), PickBan (×20),
    and PlayerStat (×10).
    """
    cur = conn.cursor()
    team_names = list(team_map.keys())
    champ_names = list(champ_map.keys())

    # Dates span 2024-01-13 → 2024-09-15  (Spring → Summer)
    start_dt = datetime(2024, 1, 13)
    end_dt = datetime(2024, 9, 15)

    # Pre-generate sorted dates for chronological order
    dates = sorted([_random_date(start_dt, end_dt) for _ in range(n_matches)])

    for i in range(n_matches):
        # --- Pick two distinct teams ------------------------------------------
        blue_name, red_name = random.sample(team_names, 2)
        blue_id = team_map[blue_name]
        red_id = team_map[red_name]

        # --- Decide winner (slight blue-side advantage, ≈52 %) ----------------
        winner_id = blue_id if random.random() < 0.52 else red_id

        # --- Game duration: 1500–2700 s (25–45 min) ---------------------------
        duration = random.randint(1500, 2700)

        # --- Tournament & patch ----------------------------------------------
        tournament = random.choice(TOURNAMENTS)
        patch = random.choice(PATCHES)

        cur.execute(
            """INSERT INTO Match
               (Tournament, Date, Patch, BlueTeamId, RedTeamId, WinnerId, GameDuration)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tournament, dates[i], patch, blue_id, red_id, winner_id, duration),
        )
        match_id = cur.lastrowid

        # --- MatchDetail (one row per side) -----------------------------------
        blue_kills = random.randint(3, 30)
        red_kills = random.randint(3, 30)
        gold_diff = random.randint(-5000, 5000)  # from blue's perspective

        # First-blood & first-dragon (mutually exclusive per match)
        fb_blue = random.choice([0, 1])
        fd_blue = random.choice([0, 1])

        for side, tid, kills, deaths, gd, fb, fd in [
            ("Blue", blue_id, blue_kills, red_kills, gold_diff, fb_blue, fd_blue),
            ("Red", red_id, red_kills, blue_kills, -gold_diff, 1 - fb_blue, 1 - fd_blue),
        ]:
            cur.execute(
                """INSERT INTO MatchDetail
                   (MatchId, TeamId, Side, TotalKills, TotalDeaths,
                    GoldDiff15, FirstBlood, FirstDragon)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (match_id, tid, side, kills, deaths, gd, fb, fd),
            )

        # --- PickBan (10 bans + 10 picks = 20 rows) --------------------------
        draft_pool = random.sample(champ_names, 20)
        order_counter = 1

        # Phase 1: 6 bans (3 per side), then 6 picks (3 per side)
        for ban_idx in range(6):
            tid = blue_id if ban_idx % 2 == 0 else red_id
            cur.execute(
                """INSERT INTO PickBan
                   (MatchId, TeamId, ChampionId, IsBan, Phase, "Order")
                   VALUES (?, ?, ?, 1, 1, ?)""",
                (match_id, tid, champ_map[draft_pool[ban_idx]], order_counter),
            )
            order_counter += 1

        for pick_idx in range(6, 12):
            tid = blue_id if pick_idx % 2 == 0 else red_id
            cur.execute(
                """INSERT INTO PickBan
                   (MatchId, TeamId, ChampionId, IsBan, Phase, "Order")
                   VALUES (?, ?, ?, 0, 1, ?)""",
                (match_id, tid, champ_map[draft_pool[pick_idx]], order_counter),
            )
            order_counter += 1

        # Phase 2: 4 bans (2 per side), then 4 picks (2 per side)
        for ban_idx in range(12, 16):
            tid = blue_id if ban_idx % 2 == 0 else red_id
            cur.execute(
                """INSERT INTO PickBan
                   (MatchId, TeamId, ChampionId, IsBan, Phase, "Order")
                   VALUES (?, ?, ?, 1, 2, ?)""",
                (match_id, tid, champ_map[draft_pool[ban_idx]], order_counter),
            )
            order_counter += 1

        for pick_idx in range(16, 20):
            tid = blue_id if pick_idx % 2 == 0 else red_id
            cur.execute(
                """INSERT INTO PickBan
                   (MatchId, TeamId, ChampionId, IsBan, Phase, "Order")
                   VALUES (?, ?, ?, 0, 2, ?)""",
                (match_id, tid, champ_map[draft_pool[pick_idx]], order_counter),
            )
            order_counter += 1

        # --- PlayerStat (5 per side = 10 rows) --------------------------------
        for side_name, tid in [(blue_name, blue_id), (red_name, red_id)]:
            roster = PLAYER_NAMES[side_name]
            # Pick 5 unique champs for this side's players
            side_champs = random.sample(champ_names, 5)
            side_kills = blue_kills if tid == blue_id else red_kills
            for role_idx, ign in enumerate(roster):
                # Distribute kills roughly; jungle/mid get more
                weight = [0.12, 0.22, 0.25, 0.28, 0.13][role_idx]
                p_kills = max(0, int(side_kills * weight + random.gauss(0, 1.5)))
                p_deaths = random.randint(0, 8)
                p_assists = random.randint(1, 15)
                p_cs = random.randint(120, 350) if role_idx != 4 else random.randint(20, 60)
                p_dmg = random.randint(5000, 35000)
                p_vision = random.randint(10, 80)

                cur.execute(
                    """INSERT INTO PlayerStat
                       (MatchId, PlayerId, ChampionId, Role,
                        Kills, Deaths, Assists, CS, DamageDealt, VisionScore)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        match_id,
                        player_map[ign],
                        champ_map[side_champs[role_idx]],
                        ROLES[role_idx],
                        p_kills,
                        p_deaths,
                        p_assists,
                        p_cs,
                        p_dmg,
                        p_vision,
                    ),
                )

        # Commit every match to ensure sequential integrity
        conn.commit()

    print(f"✅  Inserted {n_matches} matches with full detail.")


# ── Main entry point ─────────────────────────────────────────────────────────
def run_pipeline(n_matches: int = 200) -> str:
    """Execute the full pipeline end-to-end and return the DB path."""
    print("🔧  Initialising database …")
    conn = init_database()

    print("📋  Seeding teams, champions, players …")
    team_map = seed_teams(conn)
    champ_map = seed_champions(conn)
    player_map = seed_players(conn, team_map)

    print(f"🏟️  Generating {n_matches} synthetic matches …")
    generate_matches(conn, team_map, champ_map, player_map, n_matches)

    # Quick sanity check
    cur = conn.cursor()
    for table in ["Team", "Player", "Champion", "Match", "MatchDetail", "PlayerStat", "PickBan"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        print(f"   {table:>12}: {cur.fetchone()[0]:>6} rows")

    conn.close()
    print(f"\n💾  Database saved → {DB_PATH}")
    return DB_PATH


if __name__ == "__main__":
    run_pipeline()
