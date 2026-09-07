from datetime import datetime, timezone

from .persistence import persist_prediction
from .predictor import predict
from .config import MODEL_VERSION
from .timeutils import instant, utc_now
import hashlib
import json

def _kickoff_datetime(value: str) -> datetime:
    kickoff = datetime.fromisoformat(value)
    if kickoff.tzinfo is None:
        return kickoff.replace(tzinfo=timezone.utc)
    return kickoff.astimezone(timezone.utc)


def generate_pending_predictions(connection, now=None):
    now = instant(now or utc_now())
    # Date-only history is eligible only on a subsequent day. Never use future
    # results, including when a fixture is several days away.
    matches = [dict(row) for row in connection.execute("SELECT * FROM matches_v2 WHERE source='football-data' AND completed=1 AND kickoff < ? AND home_goals>=0 AND away_goals>=0 ORDER BY kickoff,id", (now.date().isoformat(),))]
    inputs_hash = hashlib.sha256(json.dumps(matches, sort_keys=True).encode()).hexdigest()
    fixtures = connection.execute("""SELECT * FROM fixtures f WHERE status='scheduled'
        AND NOT EXISTS(SELECT 1 FROM predictions p WHERE p.fixture_id=f.id AND p.model_version=?)""", (MODEL_VERSION,)).fetchall()
    generated = 0
    for fixture in fixtures:
        kickoff = _kickoff_datetime(fixture["kickoff"])
        if len(fixture['kickoff']) <= 10 or kickoff <= now:
            continue
        forecast = predict(matches, fixture["competition"], fixture["home_team"], fixture["away_team"], kickoff)
        forecast['input_metadata'] = {'sha256': inputs_hash, 'rows': len(matches), 'cutoff': now.isoformat(), 'policy': 'completed before capture day'}
        generated += persist_prediction(connection, fixture, forecast)
    return generated
