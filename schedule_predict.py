"""
schedule_predict.py — Real-time Lolesports API integration, caching, team mapping, live odds scraping (Bovada & Egamersworld), and match prediction.
"""

import os
import sys
import json
import time
import datetime
import sqlite3
import argparse
import re
import numpy as np
import pandas as pd
import requests
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

# Force UTF-8 encoding on stdout and stderr to avoid Windows console Unicode errors
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

from feature_engineering import build_feature_dataframe, get_latest_team_stats, FEATURE_COLS, TARGET_COL, DB_PATH
from model import PyTorchTabAttentionClassifier
from kelly_criterion import kelly_criterion

try:
    from autogluon_model import AutoGluonClassifier
except ImportError:
    AutoGluonClassifier = None

# --- Configuration ---
CACHE_FILE = os.path.join(os.path.dirname(__file__), "lolesports_cache.json")
API_URL = "https://esports-api.lolesports.com/persisted/gw/getSchedule"
API_HEADERS = {
    "x-api-key": "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}
EGAMERSWORLD_URL = "https://egamersworld.com/lol/matches"
BOVADA_URL = "https://www.bovada.lv/services/sports/event/coupon/events/A/description/esports"
SCRAPING_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Mapping of common LPL/LCK team names and abbreviations to the exact name in DB
TEAM_NAME_MAPPING = {
    # LPL Teams
    "ANYONE'S LEGEND": "Anyone's Legend",
    "AL": "Anyone's Legend",
    "BILIBILI GAMING": "Bilibili Gaming",
    "BLG": "Bilibili Gaming",
    "EDWARD GAMING": "EDward Gaming",
    "EDG": "EDward Gaming",
    "FUNPLUS PHOENIX": "FunPlus Phoenix",
    "FPX": "FunPlus Phoenix",
    "INVICTUS GAMING": "Invictus Gaming",
    "IG": "Invictus Gaming",
    "JD GAMING": "JD Gaming",
    "JDG": "JD Gaming",
    "LGD GAMING": "LGD Gaming",
    "LGD": "LGD Gaming",
    "LNG ESPORTS": "LNG Esports",
    "LNG": "LNG Esports",
    "NINJAS IN PYJAMAS": "Ninjas in Pyjamas",
    "NIP": "Ninjas in Pyjamas",
    "SHENZHEN NINJAS IN PYJAMAS": "Ninjas in Pyjamas",
    "OH MY GOD": "Oh My God",
    "OMG": "Oh My God",
    "ROYAL NEVER GIVE UP": "Royal Never Give Up",
    "RNG": "Royal Never Give Up",
    "TEAM WE": "Team WE",
    "WE": "Team WE",
    "THUNDERTALK GAMING": "ThunderTalk Gaming",
    "TT": "ThunderTalk Gaming",
    "TOP ESPORTS": "Top Esports",
    "TES": "Top Esports",
    "ULTRA PRIME": "Ultra Prime",
    "UP": "Ultra Prime",
    "WEIBO GAMING": "Weibo Gaming",
    "WBG": "Weibo Gaming",
    "WEIBOGAMING": "Weibo Gaming",
    
    # LCK Teams
    "BNK FEARX": "BNK FEARX",
    "FEARX": "BNK FEARX",
    "FOX": "BNK FEARX",
    "DN SOOPERS": "DN SOOPers",
    "DN SOOP": "DN SOOPers",
    "KWANGDONG FREECS": "DN SOOPers",
    "KDF": "DN SOOPers",
    "DPLUS KIA": "Dplus Kia",
    "DPLUS": "Dplus Kia",
    "DK": "Dplus Kia",
    "GEN.G": "Gen.G",
    "GEN G": "Gen.G",
    "GEN": "Gen.G",
    "HANJIN BRION": "HANJIN BRION",
    "BRION": "HANJIN BRION",
    "BRO": "HANJIN BRION",
    "HANWHA LIFE ESPORTS": "Hanwha Life Esports",
    "HANWHA": "Hanwha Life Esports",
    "HLE": "Hanwha Life Esports",
    "KT ROLSTER": "KT Rolster",
    "KT": "KT Rolster",
    "KIWOOM DRX": "Kiwoom DRX",
    "DRX": "Kiwoom DRX",
    "NONGSHIM REDFORCE": "Nongshim RedForce",
    "NONGSHIM RED FORCE": "Nongshim RedForce",
    "NS": "Nongshim RedForce",
    "T1": "T1",
}

# Mapping of team names in DB to slugs/names on betting sites
SLUG_MAP = {
    "anyone's legend": ["anyones-legend", "al", "agal"],
    "top esports": ["top-esports", "tes"],
    "bilibili gaming": ["bilibili-gaming", "blg"],
    "edward gaming": ["edward-gaming", "edg"],
    "funplus phoenix": ["funplus-phoenix", "fpx"],
    "invictus gaming": ["invictus-gaming", "ig"],
    "jd gaming": ["jd-gaming", "jdg"],
    "lgd gaming": ["lgd-gaming", "lgd"],
    "lng esports": ["lng-esports", "lng"],
    "ninjas in pyjamas": ["ninjas-in-pyjamas", "nip", "shenzhen-ninjas-in-pyjamas"],
    "oh my god": ["oh-my-god", "omg"],
    "royal never give up": ["royal-never-give-up", "rng"],
    "team we": ["team-we", "we"],
    "thundertalk gaming": ["thundertalk-gaming", "tt", "thundertalk"],
    "ultra prime": ["ultra-prime", "up"],
    "weibo gaming": ["weibo-gaming", "wbg", "weibogaming"],
    
    "bnk fearx": ["bnk-fearx", "fearx", "fox", "bnk-fearx-youth"],
    "dn soopers": ["dn-soopers", "dnsoop", "kdf", "kwangdong-freecs", "soopers-challengers", "dns-challengers"],
    "dplus kia": ["dplus-kia", "dplus", "dk", "dk-challengers"],
    "gen.g": ["gen-g", "geng", "gen", "geng-global-academy"],
    "hanjin brion": ["hanjin-brion", "brion", "bro", "ok-savings-bank-brion", "brion-challengers"],
    "hanwha life esports": ["hanwha-life-esports", "hanwha-life", "hle", "hle-challengers"],
    "kt rolster": ["kt-rolster", "kt", "kt-rolster-challengers"],
    "kiwoom drx": ["kiwoom-drx", "drx", "drx-challengers", "krx-challengers"],
    "nongshim redforce": ["nongshim-redforce", "nongshim-red-force", "nongshim", "ns", "nongshim-redforce-academy", "ns-challengers"],
    "t1": ["t1", "t1-esports-academy", "t1-challengers"],
}

def normalize_name(name):
    if not name:
        return ""
    n = name.upper().strip()
    if n in TEAM_NAME_MAPPING:
        return TEAM_NAME_MAPPING[n]
    
    n_clean = n.replace("GAMING", "").replace("ESPORTS", "").replace("TEAM", "")
    n_clean = n_clean.replace("ACADEMY", "").replace("CHALLENGERS", "").replace("YOUTH", "")
    n_clean = n_clean.replace("GLOBAL", "").replace("CLUB", "").replace("CHALLENGER", "")
    n_clean = n_clean.replace(".", "").replace(" ", "").replace("'", "").replace("-", "")
    
    for key, val in TEAM_NAME_MAPPING.items():
        k_clean = key.replace("GAMING", "").replace("ESPORTS", "").replace("TEAM", "")
        k_clean = k_clean.replace("ACADEMY", "").replace("CHALLENGERS", "").replace("YOUTH", "")
        k_clean = k_clean.replace("GLOBAL", "").replace("CLUB", "").replace("CHALLENGER", "")
        k_clean = k_clean.replace(".", "").replace(" ", "").replace("'", "").replace("-", "")
        if n_clean == k_clean or n_clean in k_clean or k_clean in n_clean:
            return val
            
    return name

def slugify(name):
    n = name.lower()
    n = re.sub(r'[^a-z0-9\s-]', '', n)
    n = re.sub(r'[\s]+', '-', n)
    return n

def fetch_schedule(use_cache=True):
    """Fetch the schedule from Lolesports API with a 1-hour cache."""
    if use_cache and os.path.exists(CACHE_FILE):
        mtime = os.path.getmtime(CACHE_FILE)
        now = time.time()
        if now - mtime < 3600:
            print("[INFO] Loading schedule from local cache...")
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARNING] Error reading cache: {e}. Fetching new data...")

    print("[INFO] Fetching live schedule from Lolesports API...")
    try:
        r = requests.get(API_URL, headers=API_HEADERS, params={"hl": "en-US"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data
    except Exception as e:
        print(f"[ERROR] Failed to fetch from API: {e}")
        if os.path.exists(CACHE_FILE):
            print("[WARNING] Falling back to expired local cache.")
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        raise e

# --- Bovada Odds Scraper ---
def fetch_bovada_odds():
    """Scrape live match odds (all markets) from Bovada's public JSON API."""
    print("[INFO] Fetching live odds from Bovada...")
    try:
        r = requests.get(BOVADA_URL, headers=SCRAPING_HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        all_events = []
        for group in data:
            for ev in group.get("events", []):
                all_events.append(ev)
        print(f"[INFO] Successfully fetched {len(all_events)} events from Bovada.")
        return all_events
    except Exception as e:
        print(f"[WARNING] Failed to fetch live odds from Bovada: {e}")
        return []

def parse_bovada_markets_for_event(ev, team_a, team_b):
    """Parse moneyline, point spread (handicap), total maps, and map exacta from Bovada event JSON."""
    display_groups = ev.get("displayGroups", [])
    
    ml_odds = {}
    hc_odds = {}
    tot_odds = {}
    cs_odds = {}
    
    for dg in display_groups:
        group_desc = dg.get("description", "")
        markets = dg.get("markets", [])
        
        if group_desc == "Game Lines":
            for mk in markets:
                mk_desc = mk.get("description")
                if mk_desc == "Moneyline":
                    for out in mk.get("outcomes", []):
                        name = out.get("description")
                        price = out.get("price", {}).get("decimal")
                        if price:
                            ml_odds[name] = float(price)
                elif mk_desc == "Point Spread":
                    for out in mk.get("outcomes", []):
                        name = out.get("description")
                        handicap = out.get("price", {}).get("handicap")
                        price = out.get("price", {}).get("decimal")
                        if price and handicap:
                            hc_odds[name] = {"handicap": float(handicap), "price": float(price)}
                elif mk_desc == "Total":
                    for out in mk.get("outcomes", []):
                        name = out.get("description")
                        handicap = out.get("price", {}).get("handicap")
                        price = out.get("price", {}).get("decimal")
                        if price and handicap:
                            tot_odds[name] = {"handicap": float(handicap), "price": float(price)}
                            
        elif group_desc == "Match Props":
            for mk in markets:
                mk_desc = mk.get("description")
                if mk_desc == "Map Exacta - Best of 3":
                    for out in mk.get("outcomes", []):
                        name = out.get("description")
                        price = out.get("price", {}).get("decimal")
                        if price:
                            cs_odds[name] = float(price)
                            
    # Combine sequences (WLW and LWW) to represent overall scoreline odds (e.g. 2-1)
    combined_cs = {}
    
    # 2-0
    for key, val in cs_odds.items():
        if key.endswith(" WW"):
            team = key[:-3].strip()
            combined_cs[f"{team} 2-0"] = val
            
    # 2-1 (combined WLW and LWW: 1 / (1/o1 + 1/o2))
    a_21 = [val for name, val in cs_odds.items() if name.startswith(team_a) and ("WLW" in name or "LWW" in name)]
    if len(a_21) == 2:
        combined_cs[f"{team_a} 2-1"] = 1.0 / sum(1.0 / o for o in a_21)
    elif len(a_21) == 1:
        combined_cs[f"{team_a} 2-1"] = a_21[0]
        
    b_21 = [val for name, val in cs_odds.items() if name.startswith(team_b) and ("WLW" in name or "LWW" in name)]
    if len(b_21) == 2:
        combined_cs[f"{team_b} 2-1"] = 1.0 / sum(1.0 / o for o in b_21)
    elif len(b_21) == 1:
        combined_cs[f"{team_b} 2-1"] = b_21[0]
        
    return {
        "ml": ml_odds,
        "handicap": hc_odds,
        "total": tot_odds,
        "correct_score": combined_cs
    }

def match_bovada_teams(bovada_a, bovada_b, blue_name, red_name):
    """Fuzzy match Bovada event participants with schedule team names in direct or reverse order."""
    blue_norm = normalize_name(blue_name).lower()
    red_norm = normalize_name(red_name).lower()
    
    bovada_a_norm = normalize_name(bovada_a).lower()
    bovada_b_norm = normalize_name(bovada_b).lower()
    
    blue_aliases = SLUG_MAP.get(blue_norm, [slugify(blue_norm)])
    red_aliases = SLUG_MAP.get(red_norm, [slugify(red_norm)])
    
    a_aliases = SLUG_MAP.get(bovada_a_norm, [slugify(bovada_a_norm)])
    b_aliases = SLUG_MAP.get(bovada_b_norm, [slugify(bovada_b_norm)])
    
    # Direct order: Blue = Bovada A, Red = Bovada B
    direct_match = False
    for ba in blue_aliases:
        for aa in a_aliases:
            if ba in aa or aa in ba:
                direct_match = True
                break
        if direct_match: break
        
    if direct_match:
        for ra in red_aliases:
            for ba2 in b_aliases:
                if ra in ba2 or ba2 in ra:
                    return "direct"
                    
    # Reverse order: Blue = Bovada B, Red = Bovada A
    reverse_match = False
    for ba in blue_aliases:
        for ba2 in b_aliases:
            if ba in ba2 or ba2 in ba:
                reverse_match = True
                break
        if reverse_match: break
        
    if reverse_match:
        for ra in red_aliases:
            for aa in a_aliases:
                if ra in aa or aa in ra:
                    return "reverse"
                    
    return None

# --- Mathematical Probability Solver for Secondary Markets ---
def solve_map_prob(match_prob, best_of=3, tolerance=1e-7):
    """Find the single map win probability p from match win probability P using binary search."""
    low, high = 0.0, 1.0
    for _ in range(50):
        mid = (low + high) / 2
        if best_of == 3:
            p_match = 3 * (mid ** 2) - 2 * (mid ** 3)
        else: # best_of == 5
            p_match = (mid ** 3) * (6 * (mid ** 2) - 15 * mid + 10)
            
        if abs(p_match - match_prob) < tolerance:
            return mid
        if p_match < match_prob:
            low = mid
        else:
            high = mid
    return (low + high) / 2

def calculate_secondary_markets(blue_match_prob, best_of=3):
    """Calculate model probabilities and fair odds for handicap, total maps, and correct score."""
    p = solve_map_prob(blue_match_prob, best_of=best_of)
    q = 1.0 - p
    
    probs = {}
    if best_of == 3:
        # Correct Scores
        probs["2-0"] = p ** 2
        probs["2-1"] = 2 * (p ** 2) * q
        probs["1-2"] = 2 * (q ** 2) * p
        probs["0-2"] = q ** 2
        
        # Totals
        probs["Over 2.5"] = 2 * p * q
        probs["Under 2.5"] = p ** 2 + q ** 2
        
        # Handicaps
        probs["Blue -1.5"] = p ** 2
        probs["Blue +1.5"] = 1.0 - q ** 2
        probs["Red -1.5"] = q ** 2
        probs["Red +1.5"] = 1.0 - p ** 2
    else: # Bo5
        # Correct Scores
        probs["3-0"] = p ** 3
        probs["3-1"] = 3 * (p ** 3) * q
        probs["3-2"] = 6 * (p ** 3) * (q ** 2)
        probs["2-3"] = 6 * (q ** 3) * (p ** 2)
        probs["1-3"] = 3 * (q ** 3) * p
        probs["0-3"] = q ** 3
        
        # Totals
        probs["Over 3.5"] = 1.0 - p**3 - q**3
        probs["Under 3.5"] = p**3 + q**3
        probs["Over 4.5"] = 6*(p**3)*(q**2) + 6*(q**3)*(p**2)
        probs["Under 4.5"] = 1.0 - probs["Over 4.5"]
        
        # Handicaps
        probs["Blue -2.5"] = p ** 3
        probs["Blue -1.5"] = p ** 3 * (4 - 3 * p)
        probs["Blue +1.5"] = 1.0 - q ** 3 * (4 - 3 * q)
        probs["Blue +2.5"] = 1.0 - q ** 3
        probs["Red -2.5"] = q ** 3
        probs["Red -1.5"] = q ** 3 * (4 - 3 * q)
        probs["Red +1.5"] = 1.0 - p ** 3 * (4 - 3 * p)
        probs["Red +2.5"] = 1.0 - p ** 3

    return probs

# --- Model & Training helpers ---
def train_model_for_league(league, model_type="lr", db_path=DB_PATH):
    """Train a classifier on the entire available historical dataset for a league."""
    df = build_feature_dataframe(db_path, league_filter=league)
    if len(df) == 0:
        raise ValueError(f"No historical data in DB for league: {league}")

    X = df[FEATURE_COLS].values
    y = df[TARGET_COL].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    if model_type == "autogluon":
        if AutoGluonClassifier is None:
            raise ImportError("AutoGluonClassifier is not available. Ensure 'autogluon' is installed.")
        model = AutoGluonClassifier(time_limit=300, presets="best_quality")
    elif league == "LPL":
        if model_type == "lr":
            model = LogisticRegression(C=0.01, solver="liblinear", random_state=42)
        elif model_type == "rf":
            model = RandomForestClassifier(max_depth=5, min_samples_leaf=2, n_estimators=100, random_state=42, n_jobs=-1)
        elif model_type == "tabattention":
            model = PyTorchTabAttentionClassifier(d_model=16, epochs=40, lr=0.01, nhead=2)
        else:
            model = LogisticRegression(C=0.01, solver="liblinear", random_state=42)
    else:  # LCK or others
        if model_type == "lr":
            model = LogisticRegression(C=1.0, solver="liblinear", random_state=42)
        elif model_type == "rf":
            model = RandomForestClassifier(max_depth=12, min_samples_leaf=5, n_estimators=100, random_state=42, n_jobs=-1)
        elif model_type == "tabattention":
            model = PyTorchTabAttentionClassifier(d_model=16, epochs=40, lr=0.01, nhead=2)
        else:
            model = LogisticRegression(C=1.0, solver="liblinear", random_state=42)

    model.fit(X_scaled, y)
    return model, scaler

def get_team_features(team_name, latest_stats, name_to_id):
    """Get the features for a team. Fall back to defaults if not found in database."""
    norm_name = normalize_name(team_name).upper()
    team_id = name_to_id.get(norm_name)
    
    if team_id is not None and team_id in latest_stats:
        return latest_stats[team_id], False
    else:
        default_stats = {
            "Elo": 1500.0,
            "ObjCtrl": 0.50,
            "AvgKills": 15.0,
            "AvgDuration": 1800.0,
            "AvgDragons": 2.0,
            "AvgTowers": 5.0,
            "AvgGold": 50000.0,
        }
        return default_stats, True

# --- Main schedule prediction ---
def predict_schedule(league="LPL", model_type="lr", db_path=DB_PATH, use_cache=True, show_markets=False):
    """Fetch the schedule, align team names, scrape Bovada, and predict outcomes for all markets."""
    print("=" * 60)
    print(f"  PREDICTING UPCOMING {league} MATCHES (3 DAYS) WITH DYNAMIC BETTING LINES")
    print("=" * 60)

    # 1. Fetch schedule
    try:
        schedule_data = fetch_schedule(use_cache=use_cache)
    except Exception:
        print("[ERROR] Cannot retrieve schedule. Exiting.")
        return

    events = schedule_data.get("data", {}).get("schedule", {}).get("events", [])
    if not events:
        print("No events found in schedule data.")
        return

    # 2. Fetch Bovada live odds (includes point spread, totals, and correct score)
    bovada_events = fetch_bovada_odds()

    # 3. Get latest team stats from DB
    latest_stats, name_to_id = get_latest_team_stats(db_path, league_filter=league)

    # 4. Train model on the entire historical dataset
    model, scaler = None, None
    if model_type != "qwen_llm":
        try:
            model, scaler = train_model_for_league(league, model_type=model_type, db_path=db_path)
            print(f"[INFO] Trained {model_type.upper()} model successfully on all historical {league} data.")
        except Exception as e:
            print(f"[ERROR] Failed to train model for {league}: {e}")
            return
    else:
        print("[INFO] Initializing Qwen-2.5-14B-Instruct for prediction...")

    now = datetime.datetime.now(datetime.timezone.utc)
    three_days_later = now + datetime.timedelta(days=3)

    predictions = []

    try:
        from tqdm import tqdm
        event_iter = tqdm(events, desc="Predicting Schedule Outcomes")
    except ImportError:
        event_iter = events

    for ev in event_iter:
        state = ev.get("state")
        start_time_str = ev.get("startTime", "")
        if not start_time_str:
            continue
        
        # Parse ISO timestamp
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

        blue_db_name = normalize_name(blue_api_name)
        red_db_name = normalize_name(red_api_name)

        blue_feats, blue_fallback = get_team_features(blue_db_name, latest_stats, name_to_id)
        red_feats, red_fallback = get_team_features(red_db_name, latest_stats, name_to_id)

        if model_type == "qwen_llm":
            from llm_predict import predict_match_probability
            proba_blue = predict_match_probability(
                blue_name=blue_api_name,
                red_name=red_api_name,
                blue_elo=blue_feats["Elo"],
                red_elo=red_feats["Elo"],
                blue_obj=blue_feats["ObjCtrl"],
                red_obj=red_feats["ObjCtrl"],
                blue_kills=blue_feats["AvgKills"],
                red_kills=red_feats["AvgKills"],
                blue_dur=blue_feats["AvgDuration"],
                red_dur=red_feats["AvgDuration"],
                blue_drag=blue_feats["AvgDragons"],
                red_drag=red_feats["AvgDragons"],
                blue_towers=blue_feats["AvgTowers"],
                red_towers=red_feats["AvgTowers"],
                blue_gold=blue_feats["AvgGold"],
                red_gold=red_feats["AvgGold"]
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

        # Match Bovada event
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

        # Best of format check (Usually Bo3, but playoffs/special events could be Bo5)
        # We can inspect the match metadata if available, default to Bo3
        best_of = 3
        
        # Calculate mathematical secondary market probabilities
        market_probs = calculate_secondary_markets(proba[1], best_of=best_of)

        bovada_odds = None
        if matched_bev:
            bovada_odds = parse_bovada_markets_for_event(matched_bev, b_team_a, b_team_b)

        predictions.append({
            "time": start_time_str,
            "blue": blue_api_name,
            "red": red_api_name,
            "blue_db": blue_db_name,
            "red_db": red_db_name,
            "blue_fallback": blue_fallback,
            "red_fallback": red_fallback,
            "predicted_winner": pred_winner,
            "winner_prob": winner_prob,
            "blue_prob": proba[1],
            "red_prob": proba[0],
            "market_probs": market_probs,
            "bovada_odds": bovada_odds,
            "direction": direction,
            "bovada_names": (b_team_a, b_team_b) if matched_bev else None,
            "best_of": best_of,
            "state": state
        })

    if not predictions:
        print(f"No upcoming/recent matches found for {league} in the 3-day window.")
        return

    # Print results in a neat format
    print("\n--- SCHEDULE, PREDICTIONS & BETTING LINES ---")
    for p in predictions:
        time_local = datetime.datetime.fromisoformat(p["time"].replace("Z", "+00:00")).astimezone()
        time_fmt = time_local.strftime("%Y-%m-%d %H:%M")
        
        fallback_str = ""
        if p["blue_fallback"] or p["red_fallback"]:
            f_teams = []
            if p["blue_fallback"]: f_teams.append(p["blue"])
            if p["red_fallback"]: f_teams.append(p["red"])
            fallback_str = f" [Fallback defaults used for: {', '.join(f_teams)}]"

        print(f"\nMatch: {time_fmt} | {p['blue']} vs {p['red']} | Status: {p['state']}{fallback_str}")
        print(f"   Model Match Winner Probabilities:")
        print(f"     * P({p['blue']} Win): {p['blue_prob']:.2%}")
        print(f"     * P({p['red']} Win): {p['red_prob']:.2%}")
        
        # 1. Match Winner Odds & Bet
        ml_odds_info = "Not found on Bovada. Using fallback 1.95."
        chosen_odds = 1.95
        
        if p["bovada_odds"]:
            # Extract moneyline odds
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

        # If detailed markets are requested
        if show_markets:
            print("\n   --- DETAILED SECONDARY MARKETS ---")
            
            # Helper to run and format Kelly
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

            # Map Handicap Market
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
                
            # Probabilities from market_probs
            blue_hc_prob = p["market_probs"]["Blue +1.5"] if hc_blue_val == 1.5 else p["market_probs"]["Blue -1.5"]
            red_hc_prob = p["market_probs"]["Red +1.5"] if hc_red_val == 1.5 else p["market_probs"]["Red -1.5"]
            
            show_kelly_for_market(f"Blue {hc_blue_val:+.1f}", blue_hc_prob, hc_blue)
            show_kelly_for_market(f"Red {hc_red_val:+.1f}", red_hc_prob, hc_red)

            # Total Maps Market
            print("   2. Total Maps (Over/Under):")
            tot_over = None
            tot_under = None
            if p["bovada_odds"]:
                tot_over = p["bovada_odds"]["total"].get("Over", {}).get("price")
                tot_under = p["bovada_odds"]["total"].get("Under", {}).get("price")
                
            show_kelly_for_market("Over 2.5", p["market_probs"]["Over 2.5"], tot_over)
            show_kelly_for_market("Under 2.5", p["market_probs"]["Under 2.5"], tot_under)

            # Correct Score Market
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
                cs_12 = p["bovada_odds"]["correct_score"].get(f"{red_key} 2-1")  # Red wins 2-1 is score 1-2 from Blue perspective
                cs_02 = p["bovada_odds"]["correct_score"].get(f"{red_key} 2-0")  # Red wins 2-0 is score 0-2 from Blue perspective
                
            show_kelly_for_market("Score 2-0", p["market_probs"]["2-0"], cs_20)
            show_kelly_for_market("Score 2-1", p["market_probs"]["2-1"], cs_21)
            show_kelly_for_market("Score 1-2", p["market_probs"]["1-2"], cs_12)
            show_kelly_for_market("Score 0-2", p["market_probs"]["0-2"], cs_02)
            
        print("   " + "-" * 50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", type=str, default="LPL", help="League to predict (LPL or LCK)")
    parser.add_argument("--model", type=str, default="lr", help="Model to use (lr, rf, tabattention)")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh fetch, bypass cache")
    parser.add_argument("--markets", action="store_true", help="Show all secondary betting markets")
    args = parser.parse_args()
    
    predict_schedule(
        league=args.league,
        model_type=args.model,
        use_cache=not args.no_cache,
        show_markets=args.markets
    )
