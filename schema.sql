-- =============================================================================
-- LPL Match Prediction System — Relational Database Schema
-- Engine: SQLite (easily portable to PostgreSQL/MySQL)
-- Convention: singular table names, PK always named "Id"
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Team
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Team (
    Id          INTEGER PRIMARY KEY AUTOINCREMENT,
    Name        TEXT    NOT NULL UNIQUE,       -- e.g. "JDG", "BLG", "T1"
    Region      TEXT    NOT NULL DEFAULT 'LPL' -- league / region tag
);

-- ---------------------------------------------------------------------------
-- 2. Player
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Player (
    Id          INTEGER PRIMARY KEY AUTOINCREMENT,
    Name        TEXT    NOT NULL,              -- in-game name (IGN)
    TeamId      INTEGER NOT NULL,
    Role        TEXT    NOT NULL,              -- Top / Jungle / Mid / Bot / Support
    FOREIGN KEY (TeamId) REFERENCES Team(Id)
);

-- ---------------------------------------------------------------------------
-- 3. Champion
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Champion (
    Id          INTEGER PRIMARY KEY AUTOINCREMENT,
    Name        TEXT    NOT NULL UNIQUE,       -- e.g. "Ahri", "Jinx"
    PrimaryRole TEXT                           -- Mage, Marksman, Tank, etc.
);

-- ---------------------------------------------------------------------------
-- 4. Match  (one row = one game in a series)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Match (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    Tournament      TEXT    NOT NULL,          -- "LPL 2024 Spring", "MSI 2024"
    Date            TEXT    NOT NULL,          -- ISO-8601  YYYY-MM-DD
    Patch           TEXT,                      -- e.g. "14.5"
    BlueTeamId      INTEGER NOT NULL,
    RedTeamId       INTEGER NOT NULL,
    WinnerId        INTEGER NOT NULL,          -- FK → Team.Id (blue or red)
    GameDuration    INTEGER NOT NULL,          -- seconds
    FOREIGN KEY (BlueTeamId) REFERENCES Team(Id),
    FOREIGN KEY (RedTeamId)  REFERENCES Team(Id),
    FOREIGN KEY (WinnerId)   REFERENCES Team(Id)
);

-- ---------------------------------------------------------------------------
-- 5. MatchDetail  (per-team aggregates for each match)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS MatchDetail (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    MatchId         INTEGER NOT NULL,
    TeamId          INTEGER NOT NULL,
    Side            TEXT    NOT NULL CHECK (Side IN ('Blue', 'Red')),
    TotalKills      INTEGER NOT NULL DEFAULT 0,
    TotalDeaths     INTEGER NOT NULL DEFAULT 0,
    GoldDiff15      INTEGER NOT NULL DEFAULT 0,  -- gold lead/deficit at 15 min
    FirstBlood      INTEGER NOT NULL DEFAULT 0,  -- 1 = secured first blood
    FirstDragon     INTEGER NOT NULL DEFAULT 0,  -- 1 = secured first dragon
    FirstTower      INTEGER NOT NULL DEFAULT 0,  -- 1 = secured first tower
    Dragons         INTEGER NOT NULL DEFAULT 0,  -- total dragons taken
    Heralds         INTEGER NOT NULL DEFAULT 0,  -- total heralds taken
    Barons          INTEGER NOT NULL DEFAULT 0,  -- total barons taken
    Towers          INTEGER NOT NULL DEFAULT 0,  -- total towers destroyed
    TotalGold       INTEGER NOT NULL DEFAULT 0,  -- total team gold earned
    FOREIGN KEY (MatchId) REFERENCES Match(Id),
    FOREIGN KEY (TeamId)  REFERENCES Team(Id)
);

-- ---------------------------------------------------------------------------
-- 6. PlayerStat  (individual player line for each match)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PlayerStat (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    MatchId         INTEGER NOT NULL,
    PlayerId        INTEGER NOT NULL,
    ChampionId      INTEGER NOT NULL,
    Role            TEXT    NOT NULL,           -- Top / Jungle / Mid / Bot / Support
    Kills           INTEGER NOT NULL DEFAULT 0,
    Deaths          INTEGER NOT NULL DEFAULT 0,
    Assists         INTEGER NOT NULL DEFAULT 0,
    CS              INTEGER NOT NULL DEFAULT 0, -- creep score
    DamageDealt     INTEGER NOT NULL DEFAULT 0,
    VisionScore     INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (MatchId)    REFERENCES Match(Id),
    FOREIGN KEY (PlayerId)   REFERENCES Player(Id),
    FOREIGN KEY (ChampionId) REFERENCES Champion(Id)
);

-- ---------------------------------------------------------------------------
-- 7. PickBan  (draft phase: each pick or ban is one row)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PickBan (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    MatchId         INTEGER NOT NULL,
    TeamId          INTEGER NOT NULL,
    ChampionId      INTEGER NOT NULL,
    IsBan           INTEGER NOT NULL DEFAULT 0, -- 1 = ban, 0 = pick
    Phase           INTEGER NOT NULL,            -- 1 or 2 (draft phase)
    "Order"         INTEGER NOT NULL,            -- sequential order in draft (1-20)
    FOREIGN KEY (MatchId)    REFERENCES Match(Id),
    FOREIGN KEY (TeamId)     REFERENCES Team(Id),
    FOREIGN KEY (ChampionId) REFERENCES Champion(Id)
);

-- ---------------------------------------------------------------------------
-- Useful indices for the feature-engineering queries
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_match_date        ON Match(Date);
CREATE INDEX IF NOT EXISTS idx_matchdetail_team  ON MatchDetail(TeamId, MatchId);
CREATE INDEX IF NOT EXISTS idx_playerstat_match  ON PlayerStat(MatchId);
CREATE INDEX IF NOT EXISTS idx_pickban_match     ON PickBan(MatchId);
