"""
scrape_oddsportal.py — Scrape historical LoL match closing odds from OddsPortal
and store them in the MatchOdds SQLite table for backtesting.

Usage:
    python scrape_oddsportal.py --league LPL --season "summer-2026"
    python scrape_oddsportal.py --league LPL --season "spring-2025" --pages 3
    python scrape_oddsportal.py --csv odds_data.csv

Dependencies:
    pip install playwright
    playwright install chromium
"""

import os
import sys
import re
import sqlite3
import argparse
import time
import datetime
import json
import csv

# Add root directory to python path
sys.path.insert(0, os.path.dirname(__file__))
from feature_engineering import DB_PATH

# OddsPortal URL patterns for LoL leagues
LEAGUE_URL_MAP = {
    "LPL": "china-lpl",
    "LCK": "south-korea-lck",
    "LEC": "europe-lec",
    "LCS": "north-america-lcs",
}


def get_results_url(league="LPL", season="summer-2026", page=1):
    """Build OddsPortal results URL for a specific league and season."""
    slug = LEAGUE_URL_MAP.get(league.upper(), league.lower())
    base = f"https://www.oddsportal.com/esports/league-of-legends/{slug}-{season}/results/"
    if page > 1:
        return f"{base}#/page/{page}/"
    return base


def parse_match_row(row_data):
    """Parse a single match row from OddsPortal into structured data."""
    try:
        teams = row_data.get("teams", [])
        if len(teams) < 2:
            return None

        team1 = teams[0].strip()
        team2 = teams[1].strip()
        odds1 = row_data.get("odds1")
        odds2 = row_data.get("odds2")
        date_str = row_data.get("date", "")
        score = row_data.get("score", "")

        if not odds1 or not odds2:
            return None

        return {
            "team1": team1,
            "team2": team2,
            "odds1": float(odds1),
            "odds2": float(odds2),
            "date": date_str,
            "score": score,
        }
    except (ValueError, TypeError):
        return None


def scrape_with_playwright(league="LPL", season="summer-2026", max_pages=3, headless=True):
    """Scrape OddsPortal results using Playwright (headless Chromium)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] Playwright not installed. Run: pip install playwright && playwright install chromium")
        return []

    all_matches = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            bypass_csp=True
        )
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        for page_num in range(1, max_pages + 1):
            url = get_results_url(league, season, page_num)
            print(f"[INFO] Scraping page {page_num}: {url}")

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(3)  # Wait for JS to render odds

                # Accept cookies if prompt appears
                try:
                    page.click("button#onetrust-accept-btn-handler", timeout=3000)
                    time.sleep(1)
                except Exception:
                    pass

                # Wait for match rows to appear
                page.wait_for_selector("div[class*='eventRow']", timeout=15000)

                # Extract match data using page.evaluate
                matches_data = page.evaluate("""
                () => {
                    const results = [];
                    const rows = document.querySelectorAll('div[class*="eventRow"]');
                    let currentDate = '';
                    
                    rows.forEach(row => {
                        try {
                            const dateEl = row.querySelector('div[class*="date"]');
                            if (dateEl && dateEl.textContent.trim()) {
                                currentDate = dateEl.textContent.trim();
                            }
                            
                            const teamEls = row.querySelectorAll('a[class*="participant-name"], span[class*="participant-name"], p[class*="participant-name"]');
                            if (teamEls.length < 2) return;
                            
                            const team1 = teamEls[0].textContent.trim();
                            const team2 = teamEls[1].textContent.trim();
                            
                            const oddsEls = row.querySelectorAll('p[class*="odds-value"], span[class*="odds-value"], div[class*="odds-value"]');
                            if (oddsEls.length < 2) return;
                            
                            const odds1 = parseFloat(oddsEls[0].textContent.trim());
                            const odds2 = parseFloat(oddsEls[1].textContent.trim());
                            
                            const scoreEl = row.querySelector('div[class*="score"], span[class*="score"]');
                            const score = scoreEl ? scoreEl.textContent.trim() : '';
                            
                            if (!isNaN(odds1) && !isNaN(odds2) && team1 && team2) {
                                results.push({
                                    teams: [team1, team2],
                                    odds1: odds1,
                                    odds2: odds2,
                                    date: currentDate,
                                    score: score
                                });
                            }
                        } catch(e) {}
                    });
                    return results;
                }
                """)

                if not matches_data:
                    # Alternative selector structure
                    matches_data = page.evaluate("""
                    () => {
                        const results = [];
                        const links = document.querySelectorAll('a[href*="/esports/"]');
                        const seen = new Set();
                        
                        links.forEach(link => {
                            try {
                                const row = link.closest('div[class*="flex"]');
                                if (!row || seen.has(row)) return;
                                seen.add(row);
                                
                                const texts = row.querySelectorAll('p, span');
                                const oddsValues = [];
                                
                                texts.forEach(el => {
                                    const text = el.textContent.trim();
                                    const num = parseFloat(text);
                                    if (!isNaN(num) && num > 1.0 && num < 50.0) {
                                        oddsValues.push(num);
                                    }
                                });
                                
                                const matchText = link.textContent.trim();
                                const parts = matchText.split(' - ');
                                if (parts.length === 2 && oddsValues.length >= 2) {
                                    results.push({
                                        teams: parts,
                                        odds1: oddsValues[0],
                                        odds2: oddsValues[1],
                                        date: '',
                                        score: ''
                                    });
                                }
                            } catch(e) {}
                        });
                        return results;
                    }
                    """)

                if matches_data:
                    for md in matches_data:
                        parsed = parse_match_row(md)
                        if parsed:
                            all_matches.append(parsed)
                    print(f"  Found {len(matches_data)} matches on page {page_num}")
                else:
                    print(f"  No matches found on page {page_num} (may be end of results)")
                    break

            except Exception as e:
                print(f"  [WARNING] Error scraping page {page_num}: {e}")
                try:
                    page.screenshot(path=f"oddsportal_error_page_{page_num}.png")
                    print(f"  [INFO] Saved screenshot of error page to oddsportal_error_page_{page_num}.png")
                except Exception:
                    pass
                break

            # Rate limiting
            time.sleep(2 + page_num)

        browser.close()

    print(f"[INFO] Total matches scraped: {len(all_matches)}")
    return all_matches


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


def parse_oddsportal_date(date_str, season):
    """Parse OddsPortal date string into ISO format YYYY-MM-DD."""
    try:
        for fmt in ["%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%Y-%m-%d"]:
            try:
                dt = datetime.datetime.strptime(date_str.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        year_match = re.search(r"(\d{4})", season)
        year = int(year_match.group(1)) if year_match else datetime.datetime.now().year

        for fmt in ["%d %b", "%d %B"]:
            try:
                dt = datetime.datetime.strptime(date_str.strip(), fmt)
                dt = dt.replace(year=year)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
    except Exception:
        pass
    return None


def save_scraped_odds(matches, db_path=DB_PATH, season=""):
    """Save scraped OddsPortal odds into the MatchOdds table."""
    if not matches:
        print("[INFO] No matches to save.")
        return 0

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

    saved = 0
    crawled_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for m in matches:
        team1 = normalize_team_name(m["team1"])
        team2 = normalize_team_name(m["team2"])
        match_date = parse_oddsportal_date(m["date"], season) if m["date"] else None

        if not match_date:
            continue

        try:
            conn.execute(
                """INSERT OR REPLACE INTO MatchOdds
                   (BlueTeamName, RedTeamName, MatchDate, Source,
                    OddsBlue, OddsRed, CrawledAt)
                   VALUES (?,?,?,?,?,?,?)""",
                (team1, team2, match_date, "oddsportal",
                 m["odds1"], m["odds2"], crawled_at)
            )
            saved += 1
        except Exception as e:
            print(f"  [WARNING] Could not save {team1} vs {team2}: {e}")

    conn.commit()
    conn.close()
    print(f"[INFO] Saved {saved} match odds to MatchOdds table (source: oddsportal)")
    return saved


def import_from_csv(csv_path, db_path=DB_PATH):
    """Import historical odds from a CSV file.
    
    CSV format: Date,Team1,Team2,Odds1,Odds2
    Example:    2026-07-15,JDG,BLG,1.45,2.55
    """
    if not os.path.isfile(csv_path):
        print(f"[ERROR] CSV file not found: {csv_path}")
        return 0

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

    saved = 0
    crawled_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO MatchOdds
                       (BlueTeamName, RedTeamName, MatchDate, Source,
                        OddsBlue, OddsRed, CrawledAt)
                       VALUES (?,?,?,?,?,?,?)""",
                    (row["Team1"].strip(), row["Team2"].strip(),
                     row["Date"].strip(), "csv_import",
                     float(row["Odds1"]), float(row["Odds2"]), crawled_at)
                )
                saved += 1
            except Exception as e:
                print(f"  [WARNING] Row error: {e}")

    conn.commit()
    conn.close()
    print(f"[INFO] Imported {saved} match odds from CSV (source: csv_import)")
    return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape historical LoL odds from OddsPortal or import from CSV.")
    parser.add_argument("--league", type=str, default="LPL", help="League (LPL, LCK, LEC, LCS)")
    parser.add_argument("--season", type=str, default="summer-2026", help="Season slug (e.g., summer-2026, spring-2025)")
    parser.add_argument("--pages", type=int, default=3, help="Number of result pages to scrape")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Show browser window")
    parser.add_argument("--csv", type=str, default=None, help="Import odds from CSV file instead of scraping")
    parser.add_argument("--db-path", type=str, default=DB_PATH, help="Path to SQLite database")
    args = parser.parse_args()

    if args.csv:
        import_from_csv(args.csv, db_path=args.db_path)
    else:
        matches = scrape_with_playwright(
            league=args.league,
            season=args.season,
            max_pages=args.pages,
            headless=args.headless
        )
        save_scraped_odds(matches, db_path=args.db_path, season=args.season)
