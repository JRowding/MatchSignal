"""Idempotent refresh command for scheduled execution."""
import os
import sys
from datetime import date
import requests
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from matchsignal.database import connect
from matchsignal.fixtures import TheSportsDBProvider, upsert_fixtures
from matchsignal.ingestion import import_season, season_code
from matchsignal.persistence import settle_predictions
from matchsignal.service import generate_pending_predictions
from matchsignal.timeutils import utc_now
from matchsignal.config import SUPPORTED_COMPETITIONS
import json
import logging

DATABASE = Path(os.environ.get("MATCHSIGNAL_DATABASE", ROOT / "data" / "matchsignal.sqlite"))

def refresh(connection):
    today = date.today()
    current = today.year if today.month >= 7 else today.year - 1
    sources, withheld = [], []
    print("Importing historical Football-Data seasons...", flush=True)
    with requests.Session() as session:
        total = sum(import_season(connection, year, session=session, diagnostics=sources)
                    for year in range(current - 3, current + 1))
        provider = TheSportsDBProvider(session)
        incoming = provider.upcoming()
    fixtures = upsert_fixtures(connection, incoming)
    current_sources = {d['competition']: d for d in sources if d['season'] == season_code(current)}
    ready_stats = {league for league in SUPPORTED_COMPETITIONS.values()
                   if all(d['status'] == 'success' for d in sources if d['competition'] == league)}
    ready_fixtures = provider.covered_competitions()
    settled = settle_predictions(connection)
    generated = generate_pending_predictions(connection, diagnostics=withheld,
                                             eligible_competitions=ready_stats & ready_fixtures)
    leagues = {}
    for league in SUPPORTED_COMPETITIONS.values():
        stat = current_sources[league]
        leagues[league] = {'statistics': stat['status'], 'latest_result': stat.get('latest_match'),
                          'fixtures': 'checked' if league in ready_fixtures else 'unverified',
                          'scheduled_found': sum(f.competition == league and f.status == 'scheduled' for f in incoming)}
    degraded = bool(withheld) or len(ready_stats & ready_fixtures) != len(SUPPORTED_COMPETITIONS)
    summary = {'status': 'degraded' if degraded else 'success', 'matches_imported': total,
               'fixtures': fixtures, 'settled': settled, 'predictions': generated,
               'leagues': leagues, 'sources': sources + provider.diagnostics, 'withheld': withheld}
    print(json.dumps(summary), flush=True)
    return summary


def main():
    logging.basicConfig(level=logging.INFO)
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get('MATCHSIGNAL_REQUIRE_LEDGER') == '1' and not DATABASE.exists():
        raise RuntimeError('Preserved prediction ledger missing; restore it before refreshing')
    connection = connect(DATABASE)
    cursor = connection.execute("INSERT INTO refresh_runs(started_at,status) VALUES(?,'running')", (utc_now().isoformat(),))
    run_id = cursor.lastrowid
    connection.commit()
    try:
        details = refresh(connection)
        connection.execute("UPDATE refresh_runs SET status=?,finished_at=?,details=? WHERE id=?",
                           (details['status'], utc_now().isoformat(), json.dumps(details), run_id))
        connection.commit()
    except Exception as exc:
        connection.rollback()
        connection.execute("UPDATE refresh_runs SET status='failed',finished_at=?,details=? WHERE id=?",
                           (utc_now().isoformat(), str(exc), run_id))
        connection.commit()
        raise
    finally:
        connection.close()

if __name__ == "__main__": main()
