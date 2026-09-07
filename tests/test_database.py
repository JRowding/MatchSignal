from matchsignal.database import connect
from matchsignal.persistence import persist_prediction, settle_predictions
from matchsignal.service import generate_pending_predictions
from datetime import datetime, timezone

def test_predictions_are_idempotent(tmp_path):
    db = connect(tmp_path / "test.sqlite")
    db.execute("INSERT INTO fixtures(external_fixture_id,competition,kickoff,home_team,away_team,status) VALUES('one','Premier League','2025-08-01','A','B','scheduled')")
    fixture = db.execute("SELECT * FROM fixtures").fetchone()
    forecast = {"home_xg": 1.4, "away_xg": .9, "confidence": "HIGH", "probabilities": {"home_win": .5}}
    persist_prediction(db, fixture, forecast); persist_prediction(db, fixture, forecast)
    assert db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 1


def test_prediction_snapshot_freezes_fixture_context(tmp_path):
    db = connect(tmp_path / "test.sqlite")
    db.execute("INSERT INTO fixtures(external_fixture_id,competition,kickoff,home_team,away_team,status) VALUES('one','Premier League','2026-08-01T15:00:00','A','B','scheduled')")
    fixture = db.execute("SELECT * FROM fixtures").fetchone()
    forecast = {"home_xg": 1.4, "away_xg": .9, "confidence": "HIGH", "probabilities": {"home_win": .72}}

    assert persist_prediction(db, fixture, forecast) == 1
    row = db.execute("SELECT fixture_kickoff,competition,home_team,away_team,market_group,probability_bucket,frozen_at FROM predictions").fetchone()

    assert row["fixture_kickoff"] == "2026-08-01T15:00:00"
    assert row["competition"] == "Premier League"
    assert row["home_team"] == "A"
    assert row["away_team"] == "B"
    assert row["market_group"] == "Match Winner"
    assert row["probability_bucket"] == "70-79%"
    assert row["frozen_at"] is not None


def test_generation_skips_fixtures_after_kickoff(tmp_path):
    db = connect(tmp_path / "test.sqlite")
    db.execute("INSERT INTO fixtures(external_fixture_id,competition,kickoff,home_team,away_team,status) VALUES('old','Premier League','2026-08-01T15:00:00','A','B','scheduled')")
    db.execute("INSERT INTO matches_v2(competition,season,kickoff,home_team,away_team,home_goals,away_goals,completed) VALUES('Premier League','2025/2026','2026-07-01','A','B',1,0,1)")
    db.commit()

    generated = generate_pending_predictions(db, now=datetime(2026, 8, 1, 15, 1, tzinfo=timezone.utc))

    assert generated == 0
    assert db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 0


def test_settlement_records_score_and_counts_only_supported_markets(tmp_path):
    db = connect(tmp_path / "test.sqlite")
    db.execute("INSERT INTO fixtures(external_fixture_id,competition,kickoff,home_team,away_team,status) VALUES('one','Premier League','2026-08-01','A','B','scheduled')")
    fixture = db.execute("SELECT * FROM fixtures").fetchone()
    forecast = {"home_xg": 1.4, "away_xg": .9, "confidence": "HIGH", "probabilities": {"home_win": .72}}
    persist_prediction(db, fixture, forecast)
    db.execute("INSERT INTO matches_v2(competition,season,kickoff,home_team,away_team,home_goals,away_goals,completed) VALUES('Premier League','2026/2027','2026-08-01','A','B',2,1,1)")
    db.commit()

    assert settle_predictions(db) == 1
    row = db.execute("SELECT actual_outcome,correct,actual_home_goals,actual_away_goals FROM predictions").fetchone()

    assert dict(row) == {"actual_outcome": 1, "correct": 1, "actual_home_goals": 2, "actual_away_goals": 1}
