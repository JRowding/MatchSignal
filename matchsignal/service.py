from datetime import datetime, timezone

from .persistence import persist_prediction
from .predictor import predict

def _kickoff_datetime(value: str) -> datetime:
    kickoff = datetime.fromisoformat(value)
    if kickoff.tzinfo is None:
        return kickoff.replace(tzinfo=timezone.utc)
    return kickoff.astimezone(timezone.utc)


def generate_pending_predictions(connection, now=None):
    now = now or datetime.now(timezone.utc)
    matches = [dict(row) for row in connection.execute("SELECT * FROM matches_v2 WHERE completed=1")]
    fixtures = connection.execute("SELECT * FROM fixtures WHERE status='scheduled'").fetchall()
    generated = 0
    for fixture in fixtures:
        kickoff = _kickoff_datetime(fixture["kickoff"])
        if kickoff <= now:
            continue
        forecast = predict(matches, fixture["competition"], fixture["home_team"], fixture["away_team"], kickoff)
        generated += persist_prediction(connection, fixture, forecast)
    return generated
