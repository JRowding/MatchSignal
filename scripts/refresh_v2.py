"""Refresh mismatch tables/fixtures; retain the existing scheduled command."""
import logging
import sys
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchsignal.refresh import SNAPSHOT, atomic_write, read_snapshot, refresh
from matchsignal.dashboard import render_dashboard, validation_report


def main():
    logging.basicConfig(level=logging.INFO)
    snapshot = refresh(read_snapshot())
    atomic_write(SNAPSHOT, json.dumps(snapshot, indent=2))
    atomic_write(ROOT / 'index.html', render_dashboard(snapshot))
    atomic_write(ROOT / 'VALIDATION_REPORT.md', validation_report(snapshot))
    print(f"{snapshot['leagues_checked']}/11 leagues checked; {len(snapshot['signals'])} MatchSignals")
    return 0 if snapshot['status'] == 'ok' else 1

if __name__ == '__main__':
    raise SystemExit(main())
