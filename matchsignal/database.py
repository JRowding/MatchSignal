import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS matches_v2 (
 id INTEGER PRIMARY KEY, competition TEXT NOT NULL, season TEXT NOT NULL, kickoff TEXT NOT NULL,
 home_team TEXT NOT NULL, away_team TEXT NOT NULL, home_goals INTEGER, away_goals INTEGER,
 home_shots INTEGER, away_shots INTEGER, home_sot INTEGER, away_sot INTEGER,
 home_corners INTEGER, away_corners INTEGER, home_fouls INTEGER, away_fouls INTEGER,
 home_yellows INTEGER, away_yellows INTEGER, home_reds INTEGER, away_reds INTEGER,
 referee TEXT, completed INTEGER NOT NULL DEFAULT 0,
 UNIQUE(competition, kickoff, home_team, away_team)
);
CREATE INDEX IF NOT EXISTS idx_matches_v2_cutoff ON matches_v2(competition, kickoff);
CREATE TABLE IF NOT EXISTS fixtures (
 id INTEGER PRIMARY KEY, external_fixture_id TEXT UNIQUE, competition TEXT NOT NULL, kickoff TEXT NOT NULL,
 home_team TEXT NOT NULL, away_team TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
 id INTEGER PRIMARY KEY, fixture_id INTEGER NOT NULL REFERENCES fixtures(id), prediction_created_at TEXT NOT NULL,
 model_version TEXT NOT NULL, home_expected_goals REAL NOT NULL, away_expected_goals REAL NOT NULL,
 market TEXT NOT NULL, selection TEXT NOT NULL, predicted_probability REAL NOT NULL CHECK(predicted_probability BETWEEN 0 AND 1),
 confidence TEXT NOT NULL, actual_outcome INTEGER, correct INTEGER, settled_at TEXT,
 UNIQUE(fixture_id, model_version, market, selection)
);
CREATE INDEX IF NOT EXISTS idx_predictions_fixture ON predictions(fixture_id);
"""

def connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection
