import csv
import html
import io
import json
import re
import sqlite3
import sys
import urllib.request
import requests
from pathlib import Path

BASE = "https://www.football-data.co.uk/"
SEASONS = ("2526", "2425", "2324")
ROOT = Path(__file__).parent
DATABASE = ROOT / "football_data.sqlite"


def fetch(path: str) -> str:
    cached = ROOT / Path(path).name
    if cached.exists():
        return cached.read_text(encoding="utf-8-sig", errors="replace")
    response = requests.get(BASE + path, headers={"User-Agent": "Mozilla/5.0"}, timeout=45)
    response.raise_for_status()
    return response.content.decode("utf-8", errors="replace")


def countries(index_html: str):
    links = re.findall(r'HREF="([a-z]+(?:m)?\.php)"[^>]*>([^<]+)', index_html, re.I)
    unique = {}
    for page, label in links:
        unique.setdefault(page.lower(), html.unescape(label).strip().replace(" Football Results", ""))
    return unique.items()


def files(page_html: str):
    pattern = r'HREF="(mmz4281/(?:' + "|".join(SEASONS) + r')/[^"?#]+\.csv)">\s*([^<]+)'
    archived = [(url, url.split("/")[1], html.unescape(league).strip())
                for url, league in re.findall(pattern, page_html, re.I)]
    current = [(f"new/{code}.csv", "current", f"Current {code} league")
               for code in re.findall(r'HREF="new/([A-Za-z0-9]+)\.csv"', page_html, re.I)]
    return archived + list(dict.fromkeys(current))


def normalise(row):
    return {key.strip(): value.strip() for key, value in row.items() if key and value is not None}


def main():
    con = sqlite3.connect(DATABASE)
    con.executescript("""
      PRAGMA journal_mode = WAL;
      CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY,
        country TEXT NOT NULL,
        competition TEXT NOT NULL,
        season TEXT NOT NULL,
        source_file TEXT NOT NULL,
        match_date TEXT,
        home_team TEXT,
        away_team TEXT,
        full_time_home_goals INTEGER,
        full_time_away_goals INTEGER,
        full_time_result TEXT,
        half_time_home_goals INTEGER,
        half_time_away_goals INTEGER,
        half_time_result TEXT,
        raw_data TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_matches_competition_season ON matches(country, competition, season);
      CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date);
      CREATE TABLE IF NOT EXISTS sources (
        source_file TEXT PRIMARY KEY,
        country TEXT NOT NULL,
        competition TEXT NOT NULL,
        season TEXT NOT NULL,
        rows_loaded INTEGER NOT NULL
      );
    """)
    con.execute("DELETE FROM sources WHERE rows_loaded = 0")
    con.commit()
    loaded_files = loaded_rows = 0
    for page, country in countries(fetch("data.php")):
        try:
            page_files = files(fetch(page))
        except Exception as error:
            print(f"Skipping {country}: {error}", file=sys.stderr)
            continue
        for source, season, competition in page_files:
            try:
                if con.execute("SELECT 1 FROM sources WHERE source_file = ?", (source,)).fetchone():
                    continue
                body = fetch(source)
                reader = csv.DictReader(io.StringIO(body))
                records = []
                for row in reader:
                    item = normalise(row)
                    home = item.get("HomeTeam") or item.get("Home")
                    away = item.get("AwayTeam") or item.get("Away")
                    if not home or not away:
                        continue
                    def number(name):
                        value = item.get(name, "")
                        return int(value) if value.isdigit() else None
                    records.append((item.get("Country") or country, item.get("League") or competition, item.get("Season") or season, source, item.get("Date"), home, away, number("FTHG") if "FTHG" in item else number("HG"), number("FTAG") if "FTAG" in item else number("AG"), item.get("FTR") or item.get("Res"), number("HTHG"), number("HTAG"), item.get("HTR"), json.dumps(item, ensure_ascii=False)))
                con.executemany("INSERT INTO matches(country, competition, season, source_file, match_date, home_team, away_team, full_time_home_goals, full_time_away_goals, full_time_result, half_time_home_goals, half_time_away_goals, half_time_result, raw_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", records)
                con.execute("INSERT INTO sources VALUES (?, ?, ?, ?, ?)", (source, country, competition, season, len(records)))
                con.commit()
                loaded_files += 1
                loaded_rows += len(records)
                print(f"Loaded {country} / {competition} / {season}: {len(records)}")
            except Exception as error:
                print(f"Skipping {source}: {error}", file=sys.stderr)
    con.execute("VACUUM")
    con.close()
    print(f"Complete: {loaded_rows} matches from {loaded_files} source files")


if __name__ == "__main__":
    main()
