from datetime import datetime, timezone
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

from .timeutils import utc_now, instant, football_day

from .config import CONFIG, MODEL_VERSION
from .scanner import LABELS

WINNER_MARKETS = {"home_win", "draw", "away_win"}
BTTS_WINNER_MARKETS = {"home_win_btts", "away_win_btts"}


def market_group(market: str) -> str:
    if market in WINNER_MARKETS:
        return "Match Winner"
    if market.startswith("over_"):
        return "Goals"
    if market.startswith("btts_"):
        return "BTTS"
    if market in BTTS_WINNER_MARKETS:
        return "BTTS + Winner"
    if "_shots_on_target_" in market:
        return "Team shots on target"
    if "_shots_" in market or market.startswith("shots_"):
        return "Team shots"
    if "fouls" in market:
        return "Team fouls"
    if "cards" in market:
        return "Team cards"
    if "corners" in market:
        return "Team corners"
    return "Other"


def probability_bucket(probability: float) -> str:
    start = min(90, int(probability * 10) * 10)
    return f"{start}-{100 if start == 90 else start + 9}%"


def market_outcome(market: str, home: int, away: int) -> bool | None:
    if type(home) is not int or type(away) is not int or min(home, away) < 0:
        raise ValueError('Final goals must be non-negative integers')
    total = home + away
    return {
        "home_win": home > away,
        "draw": home == away,
        "away_win": away > home,
        "over_0.5": total > .5,
        "over_1.5": total > 1.5,
        "over_2.5": total > 2.5,
        "over_3.5": total > 3.5,
        "btts_yes": home > 0 and away > 0,
        "btts_no": home == 0 or away == 0,
        "home_win_btts": home > away and home > 0 and away > 0,
        "away_win_btts": away > home and home > 0 and away > 0,
        "home_over_0.5": home > .5,
        "home_over_1.5": home > 1.5,
        "away_over_0.5": away > .5,
        "away_over_1.5": away > 1.5,
    }.get(market)


def persist_prediction(connection, fixture, forecast):
    """One atomic snapshot per fixture/version; no later market top-ups."""
    fixture = dict(fixture)
    version = forecast.get('model_version', MODEL_VERSION)
    created = utc_now().isoformat(timespec='seconds')
    if len(fixture['kickoff']) <= 10 or datetime.fromisoformat(fixture['kickoff']).tzinfo is None or fixture['status'] != 'scheduled' or instant(fixture['kickoff']) <= utc_now():
        return 0
    probabilities = {m: p for m, p in forecast['probabilities'].items() if m in CONFIG.enabled_markets}
    if not probabilities or any(m not in LABELS or market_outcome(m, 0, 0) is None for m in probabilities):
        raise ValueError('No supported grading rule for requested market')
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values()):
        raise ValueError('Invalid probability')
    if any(not math.isfinite(forecast[k]) or forecast[k] < 0 for k in ('home_xg', 'away_xg')):
        raise ValueError('Invalid expected goals')
    picks = set(probabilities) - WINNER_MARKETS - BTTS_WINNER_MARKETS
    for group in (WINNER_MARKETS, BTTS_WINNER_MARKETS):
        available = [m for m in forecast['probabilities'] if m in group and m in probabilities]
        if available:
            picks.add(max(available, key=probabilities.get))
    code_hash = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob('*.py')):
        code_hash.update(path.name.encode()); code_hash.update(path.read_bytes())
    payload = json.dumps({'fixture': fixture, 'forecast': forecast, 'config': asdict(CONFIG),
                          'code_sha256': code_hash.hexdigest()}, sort_keys=True, allow_nan=False)
    with connection:
        # Serialize competing writers and re-read the fixture under the write lock.
        connection.execute('UPDATE fixtures SET status=status WHERE id=?', (fixture['id'],))
        fresh = dict(connection.execute('SELECT * FROM fixtures WHERE id=?', (fixture['id'],)).fetchone())
        if fresh != fixture or instant(fixture['kickoff']) <= utc_now():
            return 0
        if connection.execute('SELECT 1 FROM predictions WHERE fixture_id=? AND model_version=?', (fixture['id'], version)).fetchone():
            return 0
        cursor = connection.execute('''INSERT INTO prediction_snapshots
            (fixture_id,model_version,frozen_at,fixture_kickoff,payload_json,payload_sha256)
            VALUES(?,?,?,?,?,?) ON CONFLICT(fixture_id,model_version) DO NOTHING''',
            (fixture['id'], version, created, fixture['kickoff'], payload, hashlib.sha256(payload.encode()).hexdigest()))
        if not cursor.rowcount:
            return 0
        snapshot_id = cursor.lastrowid
        for market, probability in probabilities.items():
            connection.execute('''INSERT INTO predictions(
                fixture_id,prediction_created_at,model_version,home_expected_goals,away_expected_goals,
                market,selection,predicted_probability,confidence,frozen_at,fixture_kickoff,
                competition,home_team,away_team,market_group,probability_bucket,evidence_status,snapshot_id,is_pick)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'verified',?,?)''',
                (fixture['id'], created, version, forecast['home_xg'], forecast['away_xg'], market,
                 LABELS[market], probability, forecast['confidence'], created, fixture['kickoff'],
                 fixture['competition'], fixture['home_team'], fixture['away_team'], market_group(market),
                 probability_bucket(probability), snapshot_id, int(market in picks)))
        if instant(fixture['kickoff']) <= utc_now():
            raise ValueError('Kickoff crossed during snapshot; transaction rolled back')
    return len(probabilities)


def record_result(connection, match, source):
    """Only an explicitly final trusted feed may enter the settlement ledger."""
    if source != 'football-data':
        return
    identity = (match['competition'], football_day(match['kickoff']), match['home_team'], match['away_team'])
    previous = connection.execute('''SELECT * FROM result_observations WHERE
        competition=? AND match_day=? AND home_team=? AND away_team=? AND source=? ORDER BY id DESC LIMIT 1''', (*identity, source)).fetchone()
    status = 'final' if match['completed'] else 'withdrawn'
    if status == 'withdrawn' and not previous:
        return
    home, away = (match['home_goals'], match['away_goals']) if match['completed'] else (previous['home_goals'], previous['away_goals'])
    market_outcome('home_win', home, away)
    result_kickoff = match.get('result_kickoff')
    if previous and previous['status'] == status and previous['kickoff'] == result_kickoff and (previous['home_goals'], previous['away_goals']) == (home, away):
        return
    connection.execute('''INSERT INTO result_observations
        (competition,match_day,home_team,away_team,home_goals,away_goals,source,retrieved_at,status,kickoff)
        VALUES(?,?,?,?,?,?,?,?,?,?)''', (*identity, home, away, source, utc_now().isoformat(), status, result_kickoff))


def settle_predictions(connection):
    """Reconcile corrections; ambiguous/rescheduled records stay out of metrics."""
    changed = 0
    today = utc_now().date().isoformat()
    with connection:
        connection.execute('UPDATE fixtures SET status=status WHERE id=-1')
        rows = connection.execute('''SELECT p.*, f.kickoff AS current_kickoff, f.status AS fixture_status,
            f.competition AS current_competition,f.home_team AS current_home,f.away_team AS current_away
            FROM predictions p JOIN fixtures f ON f.id=p.fixture_id WHERE p.evidence_status='verified' ''').fetchall()
        cache = {}
        for row in rows:
            key = (row['fixture_id'], row['fixture_kickoff'])
            if key not in cache:
                status, result = 'pending', None
                day = football_day(row['fixture_kickoff'])
                if (row['fixture_status'] not in ('scheduled', 'completed') or
                    instant(row['current_kickoff']) != instant(row['fixture_kickoff']) or
                    (row['competition'], row['home_team'], row['away_team']) !=
                    (row['current_competition'], row['current_home'], row['current_away'])):
                    status = 'fixture_changed'
                elif day < today:
                    fixtures = connection.execute('''SELECT kickoff FROM fixtures WHERE competition=? AND home_team=? AND away_team=?''',
                        (row['competition'], row['home_team'], row['away_team'])).fetchall()
                    if sum(football_day(f['kickoff']) == day for f in fixtures) != 1:
                        status = 'ambiguous_fixture'
                    else:
                        result = connection.execute('''SELECT * FROM result_observations WHERE competition=? AND match_day=?
                            AND home_team=? AND away_team=? AND source='football-data' ORDER BY id DESC LIMIT 1''',
                            (row['competition'], day, row['home_team'], row['away_team'])).fetchone()
                        status = 'settled' if result else 'missing_result'
                        if result and result['status'] != 'final':
                            status, result = 'result_withdrawn', None
                cache[key] = status, result
            status, result = cache[key]
            if result:
                if result['kickoff'] and instant(row['frozen_at']) >= instant(result['kickoff']):
                    status, result = 'late_snapshot', None
                elif not result['kickoff'] and football_day(row['frozen_at']) >= result['match_day']:
                    status, result = 'unverified_result_time', None
            outcome = market_outcome(row['market'], result['home_goals'], result['away_goals']) if result else None
            if result and outcome is None:
                status, result = 'unsupported_market', None
            observation_id = result['id'] if result else None
            if row['grading_status'] == status and row['result_observation_id'] == observation_id:
                continue
            timestamp = utc_now().isoformat()
            connection.execute('''UPDATE predictions SET actual_outcome=?,correct=?,settled_at=?,actual_home_goals=?,
                actual_away_goals=?,result_observation_id=?,grading_status=? WHERE id=?''',
                (int(outcome) if outcome is not None else None, int(outcome) if outcome is not None else None,
                 timestamp if result else None, result['home_goals'] if result else None,
                 result['away_goals'] if result else None, observation_id, status, row['id']))
            connection.execute('''INSERT INTO settlement_events(prediction_id,observation_id,outcome,status,recorded_at)
                VALUES(?,?,?,?,?)''', (row['id'], observation_id, outcome, status, timestamp))
            changed += int(result is not None)
    return changed
