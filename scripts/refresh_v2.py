"""Idempotent refresh command for scheduled execution."""
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from matchsignal.database import connect
from matchsignal.fixtures import TheSportsDBProvider, upsert_fixtures
from matchsignal.ingestion import import_season, promote_unplayed_matches_to_fixtures
from matchsignal.persistence import settle_predictions
from matchsignal.service import generate_pending_predictions
from matchsignal.timeutils import utc_now
import json
import logging

DATABASE = Path(os.environ.get("MATCHSIGNAL_DATABASE", ROOT / "data" / "matchsignal.sqlite"))

def refresh(connection):
    current = date.today().year
    print("Importing historical Football-Data seasons...", flush=True)
    total = sum(import_season(connection, year) for year in range(current - 3, current + 1))
    # FCStats' score parser does not establish final status; it must not supply
    # training results or settle the prospective tracker.
    print("Promoting unplayed matches to fixtures...", flush=True)
    fixtures = promote_unplayed_matches_to_fixtures(connection)
    print("Importing upcoming fixture provider rows...", flush=True)
    fixtures += upsert_fixtures(connection, TheSportsDBProvider().upcoming())
    print("Settling and generating predictions...", flush=True)
    if not total:
        raise RuntimeError('No historical source rows retrieved; refusing an apparently successful refresh')
    settled = settle_predictions(connection)
    generated = generate_pending_predictions(connection)
    summary = {"matches_imported": total, "fixtures": fixtures, "settled": settled, "predictions": generated}
    print(summary)
    return summary


def main():
    logging.basicConfig(level=logging.INFO)
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(DATABASE)
    cursor = connection.execute("INSERT INTO refresh_runs(started_at,status) VALUES(?,'running')", (utc_now().isoformat(),))
    run_id = cursor.lastrowid
    connection.commit()
    try:
        details = refresh(connection)
        connection.execute("UPDATE refresh_runs SET status='success',finished_at=?,details=? WHERE id=?",
                           (utc_now().isoformat(), json.dumps(details), run_id))
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
