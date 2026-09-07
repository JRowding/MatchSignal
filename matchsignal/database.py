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
 frozen_at TEXT, fixture_kickoff TEXT, competition TEXT, home_team TEXT, away_team TEXT,
 market_group TEXT, probability_bucket TEXT, actual_home_goals INTEGER, actual_away_goals INTEGER,
 UNIQUE(fixture_id, model_version, market, selection)
);
CREATE INDEX IF NOT EXISTS idx_predictions_fixture ON predictions(fixture_id);
CREATE INDEX IF NOT EXISTS idx_predictions_settled ON predictions(settled_at);
CREATE INDEX IF NOT EXISTS idx_predictions_slices ON predictions(competition, market_group, probability_bucket);
"""

PREDICTION_COLUMNS = {
    "frozen_at": "TEXT",
    "fixture_kickoff": "TEXT",
    "competition": "TEXT",
    "home_team": "TEXT",
    "away_team": "TEXT",
    "market_group": "TEXT",
    "probability_bucket": "TEXT",
    "actual_home_goals": "INTEGER",
    "actual_away_goals": "INTEGER",
}


def migrate(connection: sqlite3.Connection) -> None:
    from .persistence import market_group, probability_bucket

    existing = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(predictions)").fetchall()
    }
    for column, definition in PREDICTION_COLUMNS.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE predictions ADD COLUMN {column} {definition}")
    rows = connection.execute(
        """SELECT p.id,p.prediction_created_at,p.market,p.predicted_probability,
        f.kickoff,f.competition,f.home_team,f.away_team
        FROM predictions p JOIN fixtures f ON f.id=p.fixture_id
        WHERE p.fixture_kickoff IS NULL OR p.market_group IS NULL OR p.probability_bucket IS NULL"""
    ).fetchall()
    for row in rows:
        connection.execute(
            """UPDATE predictions
            SET frozen_at=COALESCE(frozen_at,?), fixture_kickoff=COALESCE(fixture_kickoff,?),
            competition=COALESCE(competition,?), home_team=COALESCE(home_team,?),
            away_team=COALESCE(away_team,?), market_group=COALESCE(market_group,?),
            probability_bucket=COALESCE(probability_bucket,?)
            WHERE id=?""",
            (
                row["prediction_created_at"], row["kickoff"], row["competition"],
                row["home_team"], row["away_team"], market_group(row["market"]),
                probability_bucket(row["predicted_probability"]), row["id"],
            ),
        )
    connection.commit()

def connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    migrate(connection)
    return connection
