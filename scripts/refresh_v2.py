"""Idempotent refresh command for scheduled execution."""
import os
from datetime import date
from pathlib import Path

from matchsignal.database import connect
from matchsignal.ingestion import import_season, promote_unplayed_matches_to_fixtures
from matchsignal.persistence import settle_predictions
from matchsignal.service import generate_pending_predictions

ROOT = Path(__file__).resolve().parents[1]
DATABASE = Path(os.environ.get("MATCHSIGNAL_DATABASE", ROOT / "data" / "matchsignal.sqlite"))

def main():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(DATABASE)
    current = date.today().year
    total = sum(import_season(connection, year) for year in range(current - 3, current + 1))
    fixtures = promote_unplayed_matches_to_fixtures(connection)
    settled = settle_predictions(connection)
    generated = generate_pending_predictions(connection)
    print({"matches_imported": total, "fixtures": fixtures, "settled": settled, "predictions": generated})

if __name__ == "__main__": main()
