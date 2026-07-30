"""
scrape_egamersworld.py — Scrape historical LPL/LCK closing odds from EGamersWorld
and store them in the MatchOdds SQLite table for backtesting.

This script does NOT require Playwright or Chromium. It runs using simple HTTP requests.
"""

import os
import sys
import re
import sqlite3
import argparse
import time
import datetime
import requests

# Force UTF-8 encoding on stdout and stderr to avoid Windows console Unicode errors
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add root directory to python path
sys.path.insert(0, os.path.dirname(__file__))
from feature_engineering import DB_PATH

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def normalize_team_name(name):
    """Normalize team name for matching with database names."""
    NAME_MAP = {
        "JD GAMING": "JDG",
        "JDG INTEL": "JDG",
        "BILIBILI GAMING": "BLG",
        "TOP ESPORTS": "TES",
        "WEIBO GAMING": "WBG",
        "HANWHA LIFE ESPORTS": "HLE",
        "LNG ESPORTS": "LNG",
        "TEAM WE": "WE",
        "EDWARD GAMING": "EDG",
        "ROYAL NEVER GIVE UP": "RNG",
        "FUNPLUS PHOENIX": "FPX",
        "RARE ATOM": "RA",
        "NINJAS IN PYJAMAS": "NIP",
        "INVICTUS GAMING": "IG",
        "ULTRA PRIME": "UP",
        "ANYONE'S LEGEND": "AL",
        "OH MY GOD": "OMG",
        "THUNDER TALK GAMING": "TT",
        "DPLUS KIA": "DK",
        "T1": "T1",
        "GEN.G": "GEN",
        "DRX": "DRX",
        "KT ROLSTER": "KT",
        "KWANGDONG FREECS": "KDF",
        "LIIV SANDBOX": "LSB",
        "NONGSHIM REDFORCE": "NS",
        "OK BRION": "BRO",
    }
    upper = name.strip().upper()
    return NAME_MAP.get(upper, upper)


def get_match_details_and_odds(match_url):
    """Fetch the match detail page, extract team names, start date, and closing odds."""
    full_url = f"https://egamersworld.com{match_url}"
    print(f"  Fetching details from: {full_url}")
    try:
        resp = requests.get(full_url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None

        html = resp.text

        # 1. Extract metadata (teams, start_date)
        team1_m = re.search(r'\\\"team_1\\\"\s*:\s*\\\"([^\\\"]+)\\\"', html)
        team2_m = re.search(r'\\\"team_2\\\"\s*:\s*\\\"([^\\\"]+)\\\"', html)
        date_m = re.search(r'\\\"start_date\\\"\s*:\s*\\\"([^\\\"]+)\\\"', html)

        if not team1_m:
            team1_m = re.search(r'\"team_1\"\s*:\s*\"([^\\\"]+)\"', html)
        if not team2_m:
            team2_m = re.search(r'\"team_2\"\s*:\s*\"([^\\\"]+)\"', html)
        if not date_m:
            date_m = re.search(r'\"start_date\"\s*:\s*\"([^\\\"]+)\"', html)

        if not team1_m or not team2_m or not date_m:
            print("    [WARNING] Missing metadata in match details.")
            return None

        team1 = team1_m.group(1)
        team2 = team2_m.group(1)
        # Extract YYYY-MM-DD from start_date (e.g. 2026-07-30T10:00:00.000Z)
        match_date = date_m.group(1)[:10]

        # 2. Extract odds snapshots
        pattern_escaped = r'\\\"date\\\"\s*:\s*\\\"([^\\\"]+)\\\"\s*,\s*\\\"k1\\\"\s*:\s*([0-9.]+)\s*,\s*\\\"k2\\\"\s*:\s*([0-9.]+)'
        pattern_normal = r'\"date\"\s*:\s*\"([^\\\"]+)\"\s*,\s*\"k1\"\s*:\s*([0-9.]+)\s*,\s*\"k2\"\s*:\s*([0-9.]+)'

        matches = re.findall(pattern_escaped, html)
        if not matches:
            matches = re.findall(pattern_normal, html)

        if not matches:
            print("    [WARNING] No odds snapshots found on detail page.")
            return None

        # Sort snapshots and take the latest one (closing odds)
        sorted_matches = sorted(matches, key=lambda x: x[0])
        latest = sorted_matches[-1]
        odds1 = float(latest[1])
        odds2 = float(latest[2])

        return {
            "team1": team1,
            "team2": team2,
            "date": match_date,
            "odds1": odds1,
            "odds2": odds2
        }
    except Exception as e:
        print(f"    [WARNING] Error fetching/parsing match details: {e}")
    return None


def scrape_egamersworld(league="LPL", target_url=None, db_path=DB_PATH):
    """Scrape EGamersWorld match URLs and save odds to SQLite."""
    print("=" * 60)
    print(f"  SCRAPING HISTORICAL {league} ODDS FROM EGAMERSWORLD")
    if target_url:
        print(f"  Target URL: {target_url}")
    print("=" * 60)

    url = target_url or "https://egamersworld.com/lol/matches/history"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[ERROR] Failed to fetch target page: Status code {resp.status_code}")
            return 0
        html = resp.text
    except Exception as e:
        print(f"[ERROR] Error loading target URL: {e}")
        return 0

    # Extract all match detail links: /lol/match/<event-id>/<slug>
    links = re.findall(r'href=["\'](/lol/match/[A-Za-z0-9]+/[-a-zA-Z0-9_]+)["\']', html)
    unique_links = sorted(list(set(links)))
    print(f"[INFO] Found {len(unique_links)} unique match detail links on the target page.")

    # Filter links: if we are scanning a general page, we want only league matchups.
    # Event URLs already filter matches by design, so we filter only for the general page.
    filtered_links = []
    for link in unique_links:
        # Check if the slug contains the league filter or typical league indicators
        # If target_url is specified, we assume all links on that page are relevant (e.g. event page).
        if target_url:
            filtered_links.append(link)
        else:
            # For general page, filter by team name mapping or league slug in EGW matches if possible.
            # We can also just fetch all links and filter at the metadata level! This is much more reliable.
            filtered_links.append(link)

    # Connect to DB to save odds
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS MatchOdds (
            Id              INTEGER PRIMARY KEY AUTOINCREMENT,
            BlueTeamName    TEXT NOT NULL,
            RedTeamName     TEXT NOT NULL,
            MatchDate       TEXT NOT NULL,
            Source          TEXT NOT NULL DEFAULT 'bovada',
            OddsBlue        REAL NOT NULL,
            OddsRed         REAL NOT NULL,
            HcBluePrice     REAL, HcBlueVal REAL,
            HcRedPrice      REAL, HcRedVal  REAL,
            TotalOverPrice  REAL, TotalUnderPrice REAL,
            Cs20 REAL, Cs21 REAL, Cs12 REAL, Cs02 REAL,
            CrawledAt       TEXT NOT NULL,
            UNIQUE(BlueTeamName, RedTeamName, MatchDate, Source)
        )
    """)

    saved_count = 0
    crawled_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Load known team names in database to filter and match
    db_teams = set()
    try:
        for row in conn.execute("SELECT Name FROM Team").fetchall():
            db_teams.add(row[0].strip().upper())
            db_teams.add(normalize_team_name(row[0]).strip().upper())
    except Exception:
        pass

    for idx, match_url in enumerate(filtered_links):
        print(f"[{idx+1}/{len(filtered_links)}] Processing match...")
        
        # 1. Fetch details (teams, date, odds)
        details = get_match_details_and_odds(match_url)
        if not details:
            continue

        t1 = normalize_team_name(details["team1"])
        t2 = normalize_team_name(details["team2"])
        m_date = details["date"]

        # 2. Filter: Only save if at least one of the teams is a known team in our prediction database
        # (This automatically filters out other leagues like LFL, CBLOL, etc. when parsing the general page!)
        t1_upper = t1.upper()
        t2_upper = t2.upper()
        
        # When scraping a specific event page, the user knows what they are scraping, so we can save it.
        # But for general history page, we verify against known teams to filter matches.
        if not target_url and (t1_upper not in db_teams and t2_upper not in db_teams):
            print(f"    -> [SKIP] Match {t1} vs {t2} does not belong to LPL/LCK teams in database.")
            continue

        # 3. Check if already exists in DB
        cursor = conn.cursor()
        cursor.execute(
            "SELECT Id FROM MatchOdds WHERE BlueTeamName=? AND RedTeamName=? AND MatchDate=? AND Source='egamersworld'",
            (t1, t2, m_date)
        )
        if cursor.fetchone():
            print(f"    -> [SKIP] Odds for {t1} vs {t2} ({m_date}) already saved in database.")
            continue

        # 4. Insert or Replace
        try:
            conn.execute(
                """INSERT OR REPLACE INTO MatchOdds
                   (BlueTeamName, RedTeamName, MatchDate, Source, OddsBlue, OddsRed, CrawledAt)
                   VALUES (?,?,?,?,?,?,?)""",
                (t1, t2, m_date, "egamersworld", details["odds1"], details["odds2"], crawled_at)
            )
            conn.commit()
            saved_count += 1
            print(f"    -> [DB] Saved: {t1} ({details['odds1']:.2f}) vs {t2} ({details['odds2']:.2f}) on {m_date}")
        except Exception as e:
            print(f"    -> [DB] Warning: Could not save odds: {e}")
        
        time.sleep(1.5)

    conn.close()
    print(f"[INFO] Completed. Saved {saved_count} new match odds to MatchOdds table (source: egamersworld)")
    return saved_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape historical LPL/LCK odds from EGamersWorld.")
    parser.add_argument("--league", type=str, default="LPL", help="League filter (LPL or LCK)")
    parser.add_argument("--url", type=str, default=None, help="Scrape all matches from a specific tournament event URL or match URL directly")
    parser.add_argument("--db-path", type=str, default=DB_PATH, help="Path to SQLite database")
    args = parser.parse_args()

    scrape_egamersworld(league=args.league, target_url=args.url, db_path=args.db_path)
