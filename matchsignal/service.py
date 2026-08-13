from datetime import datetime

from .persistence import persist_prediction
from .predictor import predict

def generate_pending_predictions(connection):
    matches = [dict(row) for row in connection.execute("SELECT * FROM matches_v2 WHERE completed=1")]
    fixtures = connection.execute("SELECT * FROM fixtures WHERE status='scheduled'").fetchall()
    generated = 0
    for fixture in fixtures:
        already_exists = connection.execute("SELECT 1 FROM predictions WHERE fixture_id=?", (fixture["id"],)).fetchone()
        if already_exists: continue
        forecast = predict(matches, fixture["competition"], fixture["home_team"], fixture["away_team"], datetime.fromisoformat(fixture["kickoff"]))
        persist_prediction(connection, fixture, forecast); generated += 1
    return generated
