import datetime as dt
import re
import sqlite3
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).parent
DB = ROOT / "football_data.sqlite"
LIVE_URL = "https://www.livescore.bz/api.livescore.0.1.js"


def key(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"\b(fc|cf|ac|afc|fk|sc|the)\b", " ", value)
    return re.sub(r"[^a-z0-9]", "", value)


def parse(html):
    section = None
    fixtures = []
    for chunk in re.split(r"(<h4>.*?</h4>)", html, flags=re.I | re.S):
        heading = re.fullmatch(r"<h4>(.*?)</h4>", chunk, flags=re.I | re.S)
        if heading:
            title = re.sub(r"<.*?>", "", heading.group(1)).strip()
            if ":" in title:
                section = tuple(part.strip().title() for part in title.split(":", 1))
            else:
                section = None
            continue
        if not section:
            continue
        pattern = r"<span[^>]*>([^<]+)</span>\s*([^<]+?)\s*-\s*([^<]+?)\s*<a[^>]*class=\"(sched|live|fin)\""
        for status, home, away, state in re.findall(pattern, chunk, flags=re.I):
            if state.lower() == "sched":
                fixtures.append((*section, re.sub(r"\s+", " ", home).strip(), re.sub(r"\s+", " ", away).strip(), status.strip()))
    return fixtures


def main():
    response = requests.get(LIVE_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=45)
    response.raise_for_status()
    fixtures = parse(response.text)
    con = sqlite3.connect(DB)
    con.executescript("""
      CREATE TABLE IF NOT EXISTS live_fixtures (
        id INTEGER PRIMARY KEY,
        snapshot_at TEXT NOT NULL,
        country TEXT NOT NULL,
        competition TEXT NOT NULL,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        scheduled_time TEXT
      );
      CREATE TABLE IF NOT EXISTS prediction_candidates (
        fixture_id INTEGER PRIMARY KEY,
        country_match TEXT NOT NULL,
        competition_match TEXT NOT NULL,
        home_history INTEGER NOT NULL,
        away_history INTEGER NOT NULL,
        confidence TEXT NOT NULL,
        FOREIGN KEY(fixture_id) REFERENCES live_fixtures(id)
      );
      DELETE FROM prediction_candidates;
      DELETE FROM live_fixtures;
    """)
    historical = {}
    for country, competition, home, away in con.execute("SELECT country, competition, home_team, away_team FROM matches"):
        for team in (home, away):
            historical.setdefault((key(country), key(team)), []).append(competition)
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    candidates = 0
    for country, competition, home, away, kickoff in fixtures:
        cur = con.execute("INSERT INTO live_fixtures(snapshot_at,country,competition,home_team,away_team,scheduled_time) VALUES(?,?,?,?,?,?)", (stamp, country, competition, home, away, kickoff))
        home_rows = historical.get((key(country), key(home)), [])
        away_rows = historical.get((key(country), key(away)), [])
        if not home_rows or not away_rows:
            continue
        home_leagues = {key(x) for x in home_rows}
        away_leagues = {key(x) for x in away_rows}
        league_key = key(competition)
        league_ok = league_key in home_leagues and league_key in away_leagues
        confidence = "high" if league_ok and len(home_rows) >= 5 and len(away_rows) >= 5 else "review"
        con.execute("INSERT INTO prediction_candidates VALUES(?,?,?,?,?,?)", (cur.lastrowid, "exact", "exact" if league_ok else "country-only", len(home_rows), len(away_rows), confidence))
        candidates += 1
    con.commit()
    print(f"Captured {len(fixtures)} scheduled fixtures; matched {candidates} historical candidates")
    con.close()


if __name__ == "__main__":
    main()
