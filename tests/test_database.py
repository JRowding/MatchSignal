from datetime import datetime, timezone
import json
import sqlite3
import pytest

from matchsignal.database import connect
from matchsignal.persistence import persist_prediction, settle_predictions, record_result, market_outcome
from matchsignal.service import generate_pending_predictions
from matchsignal.fixtures import Fixture, upsert_fixtures
from matchsignal.config import CONFIG


def seed(db, kickoff="2099-08-01T14:00:00+00:00", external="one"):
    upsert_fixtures(db, [Fixture(external, "Premier League", kickoff, "A", "B")])
    return db.execute("SELECT * FROM fixtures WHERE external_fixture_id=?", (external,)).fetchone()


def forecast():
    return {"home_xg": 1.4, "away_xg": .9, "confidence": "HIGH", "probabilities": {
        "home_win": .72, "draw": .18, "away_win": .1, "over_2.5": .7,
        "btts_yes": .6, "home_win_btts": .5, "away_win_btts": .04}}


def final_result(db, monkeypatch, home=2, away=1):
    monkeypatch.setattr("matchsignal.persistence.utc_now", lambda: datetime(2099, 8, 3, tzinfo=timezone.utc))
    record_result(db, {"competition": "Premier League", "kickoff": "2099-08-01", "home_team": "A", "away_team": "B", "home_goals": home, "away_goals": away, "completed": 1}, "football-data")
    db.commit()


def test_atomic_snapshot_is_idempotent_and_rejects_topups(tmp_path):
    db=connect(tmp_path / "test.sqlite"); fixture=seed(db)
    assert persist_prediction(db, fixture, forecast()) == 7
    altered=forecast(); altered["probabilities"]["home_win"]=.99
    assert persist_prediction(db, fixture, altered) == 0
    assert db.execute("SELECT predicted_probability FROM predictions WHERE market='home_win'").fetchone()[0] == .72
    assert db.execute("SELECT COUNT(*) FROM prediction_snapshots").fetchone()[0] == 1
    assert db.execute("SELECT SUM(is_pick) FROM predictions").fetchone()[0] == 4
    payload=json.loads(db.execute("SELECT payload_json FROM prediction_snapshots").fetchone()[0])
    assert payload["forecast"] == forecast()
    assert payload["code_sha256"]


def test_freeze_database_enforcement_and_restart(tmp_path):
    path=tmp_path / "test.sqlite"; db=connect(path); fixture=seed(db)
    persist_prediction(db, fixture, forecast())
    for query in ("UPDATE predictions SET predicted_probability=.99", "DELETE FROM predictions", "UPDATE prediction_snapshots SET payload_json='{}'"):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(query)
        db.rollback()
    db.close(); db=connect(path)
    assert persist_prediction(db, db.execute("SELECT * FROM fixtures").fetchone(), forecast()) == 0
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_reject_late_unknown_time_and_forged_snapshot(tmp_path):
    db=connect(tmp_path / "test.sqlite"); fixture=seed(db, "2020-08-01T14:00:00+00:00")
    assert persist_prediction(db, fixture, forecast()) == 0
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO prediction_snapshots(fixture_id,model_version,frozen_at,fixture_kickoff,payload_json,payload_sha256) VALUES(1,'fake','2020-07-01','2020-08-01','{}','fake')")
    db.rollback()
    db.execute("UPDATE fixtures SET kickoff='2099-08-01'"); db.commit()
    assert persist_prediction(db, db.execute("SELECT * FROM fixtures").fetchone(), forecast()) == 0


def test_settlement_date_matching_corrections_and_idempotency(tmp_path, monkeypatch):
    db=connect(tmp_path / "test.sqlite"); fixture=seed(db); persist_prediction(db, fixture, forecast())
    final_result(db, monkeypatch)
    assert settle_predictions(db) == 7
    assert settle_predictions(db) == 0
    final_result(db, monkeypatch, 0, 0)
    assert settle_predictions(db) == 7
    row=db.execute("SELECT * FROM predictions WHERE market='home_win'").fetchone()
    assert row["actual_outcome"] == 0 and row["predicted_probability"] == .72
    assert db.execute("SELECT COUNT(*) FROM settlement_events").fetchone()[0] == 14
    assert db.execute("SELECT COUNT(*) FROM result_observations").fetchone()[0] == 2
    final_result(db, monkeypatch, 0, 0)
    assert db.execute("SELECT COUNT(*) FROM result_observations").fetchone()[0] == 2


@pytest.mark.parametrize("status", ["postponed", "abandoned", "cancelled", "identity_conflict"])
def test_nonfinal_fixture_never_gets_grade(tmp_path, monkeypatch, status):
    db=connect(tmp_path / "test.sqlite"); persist_prediction(db, seed(db), forecast())
    db.execute("UPDATE fixtures SET status=?", (status,)); db.commit()
    final_result(db, monkeypatch)
    assert settle_predictions(db) == 0
    assert db.execute("SELECT DISTINCT grading_status FROM predictions").fetchone()[0] == "fixture_changed"


def test_reschedule_does_not_rewrite_prediction_or_grade_new_fixture(tmp_path, monkeypatch):
    db=connect(tmp_path / "test.sqlite"); persist_prediction(db, seed(db), forecast())
    seed(db, "2099-08-02T14:00:00+00:00")
    final_result(db, monkeypatch)
    assert settle_predictions(db) == 0
    assert db.execute("SELECT fixture_kickoff FROM predictions").fetchone()[0] == "2099-08-01T14:00:00+00:00"


def test_duplicate_provider_ids_map_to_one_fixture(tmp_path):
    db=connect(tmp_path / "test.sqlite"); seed(db)
    upsert_fixtures(db, [Fixture("two", "Premier League", "2099-08-01T14:00:00+00:00", "A", "B")])
    assert db.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM fixture_aliases").fetchone()[0] == 1


def test_legacy_duplicate_fixtures_are_ambiguous(tmp_path, monkeypatch):
    db=connect(tmp_path / "test.sqlite"); persist_prediction(db, seed(db), forecast())
    db.execute("INSERT INTO fixtures(external_fixture_id,competition,kickoff,home_team,away_team,status) VALUES('dup','Premier League','2099-08-01T15:00:00+00:00','A','B','scheduled')"); db.commit()
    final_result(db, monkeypatch)
    assert settle_predictions(db) == 0
    assert db.execute("SELECT grading_status FROM predictions").fetchone()[0] == "ambiguous_fixture"


def test_real_generation_has_no_timezone_crash_and_skips_existing(tmp_path):
    db=connect(tmp_path / "test.sqlite"); seed(db)
    db.execute("INSERT INTO matches_v2(competition,season,kickoff,home_team,away_team,home_goals,away_goals,completed,source) VALUES('Premier League','2025','2025-01-01','A','B',1,0,1,'football-data')"); db.commit()
    assert generate_pending_predictions(db) == 7
    assert generate_pending_predictions(db) == 0


def test_invalid_probability_rolls_back_entire_batch(tmp_path):
    db=connect(tmp_path / "test.sqlite"); fixture=seed(db); prediction=forecast()
    prediction["probabilities"]["away_win"]=float('nan')
    with pytest.raises(ValueError): persist_prediction(db, fixture, prediction)
    assert db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM prediction_snapshots").fetchone()[0] == 0


@pytest.mark.parametrize("home,away", [(0,0),(1,1),(1,0),(0,1),(2,1),(1,2),(2,2),(5,0)])
def test_every_enabled_market_truth_table(home, away):
    expected={"home_win": home>away, "draw": home==away, "away_win": away>home,
        "over_2.5": home+away>=3, "btts_yes": min(home,away)>0,
        "home_win_btts": home>away and away>0, "away_win_btts": away>home and home>0}
    assert set(expected) == set(CONFIG.enabled_markets)
    for market, result in expected.items(): assert market_outcome(market, home, away) == result


@pytest.mark.parametrize("goals", [(None,1),(-1,0),(1.5,0),(True,0)])
def test_invalid_results_rejected(goals):
    with pytest.raises(ValueError): market_outcome('home_win', *goals)
