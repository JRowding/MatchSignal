import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA recursive_triggers = ON;
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
    "evidence_status": "TEXT NOT NULL DEFAULT 'legacy_unverified'",
    "snapshot_id": "INTEGER REFERENCES prediction_snapshots(id)",
    "is_pick": "INTEGER NOT NULL DEFAULT 0",
    "result_observation_id": "INTEGER",
    "grading_status": "TEXT NOT NULL DEFAULT 'pending'",
}


def migrate(connection: sqlite3.Connection) -> None:
    match_columns = {r['name'] for r in connection.execute('PRAGMA table_info(matches_v2)')}
    if 'source' not in match_columns:
        connection.execute("ALTER TABLE matches_v2 ADD COLUMN source TEXT NOT NULL DEFAULT 'legacy_unverified'")
    existing = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(predictions)").fetchall()
    }
    for column, definition in PREDICTION_COLUMNS.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE predictions ADD COLUMN {column} {definition}")
    # Do not manufacture frozen context from a mutable fixture during migration.
    # Existing records remain explicitly unverified.
    connection.execute("CREATE INDEX IF NOT EXISTS idx_predictions_slices ON predictions(competition, market_group, probability_bucket)")
    connection.executescript(INTEGRITY_SCHEMA)
    connection.commit()

def connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    migrate(connection)
    return connection


INTEGRITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS refresh_runs (
 id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
 status TEXT NOT NULL, details TEXT
);
CREATE TABLE IF NOT EXISTS prediction_snapshots (
 id INTEGER PRIMARY KEY, fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
 model_version TEXT NOT NULL, frozen_at TEXT NOT NULL, fixture_kickoff TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
 UNIQUE(fixture_id, model_version)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_predictions_snapshot_market ON predictions(snapshot_id,market) WHERE snapshot_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS result_observations (
 id INTEGER PRIMARY KEY, competition TEXT NOT NULL, match_day TEXT NOT NULL,
 home_team TEXT NOT NULL, away_team TEXT NOT NULL, home_goals INTEGER NOT NULL CHECK(home_goals>=0),
 away_goals INTEGER NOT NULL CHECK(away_goals>=0), source TEXT NOT NULL, retrieved_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'final', kickoff TEXT
);
CREATE INDEX IF NOT EXISTS idx_results_identity ON result_observations(competition,match_day,home_team,away_team,id);
CREATE INDEX IF NOT EXISTS idx_fixtures_identity ON fixtures(competition,home_team,away_team,kickoff);
CREATE INDEX IF NOT EXISTS idx_predictions_verified_model ON predictions(evidence_status,model_version,grading_status,is_pick);
CREATE TABLE IF NOT EXISTS settlement_events (
 id INTEGER PRIMARY KEY, prediction_id INTEGER NOT NULL REFERENCES predictions(id),
 observation_id INTEGER REFERENCES result_observations(id), outcome INTEGER,
 status TEXT NOT NULL, recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fixture_aliases (
 external_id TEXT PRIMARY KEY, fixture_id INTEGER NOT NULL REFERENCES fixtures(id)
);
CREATE TRIGGER IF NOT EXISTS snapshot_no_update BEFORE UPDATE ON prediction_snapshots
 BEGIN SELECT RAISE(ABORT,'Frozen snapshot is immutable'); END;
CREATE TRIGGER IF NOT EXISTS snapshot_no_delete BEFORE DELETE ON prediction_snapshots
 BEGIN SELECT RAISE(ABORT,'Frozen snapshot is immutable'); END;
CREATE TRIGGER IF NOT EXISTS snapshot_before_kickoff BEFORE INSERT ON prediction_snapshots
 WHEN julianday(NEW.fixture_kickoff) IS NULL OR julianday(NEW.frozen_at) IS NULL
 OR julianday(NEW.fixture_kickoff)<=julianday('now')
 OR abs(julianday(NEW.frozen_at)-julianday('now'))>1.0/1440
 BEGIN SELECT RAISE(ABORT,'Snapshot must be captured before kickoff with current clock'); END;
CREATE TRIGGER IF NOT EXISTS prediction_no_delete BEFORE DELETE ON predictions
 BEGIN SELECT RAISE(ABORT,'Historical predictions cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS prediction_frozen_fields BEFORE UPDATE OF
 fixture_id,prediction_created_at,model_version,home_expected_goals,away_expected_goals,
 market,selection,predicted_probability,confidence,frozen_at,fixture_kickoff,competition,
 home_team,away_team,market_group,probability_bucket,evidence_status,snapshot_id,is_pick ON predictions
 BEGIN SELECT RAISE(ABORT,'Frozen prediction fields are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prediction_verified_insert BEFORE INSERT ON predictions
 WHEN NEW.evidence_status='verified' AND (
 NEW.snapshot_id IS NULL OR NOT EXISTS(SELECT 1 FROM prediction_snapshots s
 WHERE s.id=NEW.snapshot_id AND s.fixture_id=NEW.fixture_id AND s.model_version=NEW.model_version
 AND s.frozen_at=NEW.frozen_at AND s.fixture_kickoff=NEW.fixture_kickoff
 AND NEW.prediction_created_at=s.frozen_at
 AND NEW.competition=json_extract(s.payload_json,'$.fixture.competition')
 AND NEW.home_team=json_extract(s.payload_json,'$.fixture.home_team')
 AND NEW.away_team=json_extract(s.payload_json,'$.fixture.away_team')
 AND NEW.home_expected_goals=json_extract(s.payload_json,'$.forecast.home_xg')
 AND NEW.away_expected_goals=json_extract(s.payload_json,'$.forecast.away_xg')
 AND NEW.confidence=json_extract(s.payload_json,'$.forecast.confidence')
 AND EXISTS(SELECT 1 FROM json_each(s.payload_json,'$.forecast.probabilities') j
 WHERE j.key=NEW.market AND j.value=NEW.predicted_probability))
 OR julianday(NEW.fixture_kickoff)<=julianday('now'))
 BEGIN SELECT RAISE(ABORT,'Verified prediction requires a pre-match snapshot'); END;
CREATE TRIGGER IF NOT EXISTS result_no_update BEFORE UPDATE ON result_observations
 BEGIN SELECT RAISE(ABORT,'Append result corrections'); END;
CREATE TRIGGER IF NOT EXISTS result_no_delete BEFORE DELETE ON result_observations
 BEGIN SELECT RAISE(ABORT,'Result observations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS settlement_no_update BEFORE UPDATE ON settlement_events
 BEGIN SELECT RAISE(ABORT,'Settlement events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS settlement_no_delete BEFORE DELETE ON settlement_events
 BEGIN SELECT RAISE(ABORT,'Settlement events are immutable'); END;
"""
