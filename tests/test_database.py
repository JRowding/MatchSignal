from matchsignal.database import connect
from matchsignal.persistence import persist_prediction

def test_predictions_are_idempotent(tmp_path):
    db = connect(tmp_path / "test.sqlite")
    db.execute("INSERT INTO fixtures(external_fixture_id,competition,kickoff,home_team,away_team,status) VALUES('one','Premier League','2025-08-01','A','B','scheduled')")
    fixture = db.execute("SELECT * FROM fixtures").fetchone()
    forecast = {"home_xg": 1.4, "away_xg": .9, "confidence": "HIGH", "probabilities": {"home_win": .5}}
    persist_prediction(db, fixture, forecast); persist_prediction(db, fixture, forecast)
    assert db.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 1
