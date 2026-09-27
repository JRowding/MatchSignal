"""Build the static dashboard from cached data without fetching feeds."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchsignal.dashboard import render_dashboard, match_day, match_time
from matchsignal.refresh import atomic_write, read_snapshot

def main():
    atomic_write(ROOT / 'index.html', render_dashboard(read_snapshot()))

if __name__ == '__main__': main()
