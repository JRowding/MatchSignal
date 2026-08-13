"""Robust Football-Data.co.uk CSV import for the supported English leagues."""
import csv
import io
import logging
from datetime import datetime

import requests

from .config import SUPPORTED_COMPETITIONS
from .normalization import canonical_team

LOG = logging.getLogger(__name__)
BASE = "https://www.football-data.co.uk/mmz4281"

def season_code(start_year: int) -> str:
    return f"{str(start_year)[-2:]}{str(start_year + 1)[-2:]}"

def _integer(row, field):
    value = row.get(field, "").strip()
    return int(value) if value.lstrip("-").isdigit() else None

def _date(value: str) -> str | None:
    for pattern in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try: return datetime.strptime(value.strip(), pattern).date().isoformat()
        except ValueError: pass
    return None

def parse_csv(content: str, competition: str, season: str) -> list[dict]:
    rows = []
    for row in csv.DictReader(io.StringIO(content.lstrip("\ufeff"))):
        home, away, kickoff = row.get("HomeTeam", "").strip(), row.get("AwayTeam", "").strip(), _date(row.get("Date", ""))
        if not home or not away or not kickoff: continue
        rows.append({
            "competition": competition, "season": season, "kickoff": kickoff,
            "home_team": canonical_team(home), "away_team": canonical_team(away),
            "home_goals": _integer(row, "FTHG"), "away_goals": _integer(row, "FTAG"),
            "home_shots": _integer(row, "HS"), "away_shots": _integer(row, "AS"),
            "home_sot": _integer(row, "HST"), "away_sot": _integer(row, "AST"),
            "home_corners": _integer(row, "HC"), "away_corners": _integer(row, "AC"),
            "home_fouls": _integer(row, "HF"), "away_fouls": _integer(row, "AF"),
            "home_yellows": _integer(row, "HY"), "away_yellows": _integer(row, "AY"),
            "home_reds": _integer(row, "HR"), "away_reds": _integer(row, "AR"),
            "referee": row.get("Referee") or None,
            "completed": int(_integer(row, "FTHG") is not None and _integer(row, "FTAG") is not None),
        })
    return rows

def import_season(connection, start_year: int, session=requests) -> int:
    code = season_code(start_year); imported = 0
    for source_code, competition in SUPPORTED_COMPETITIONS.items():
        response = session.get(f"{BASE}/{code}/{source_code}.csv", timeout=45, headers={"User-Agent": "MatchSignal/2.0"})
        if response.status_code == 404:
            LOG.info("Source unavailable", extra={"competition": competition, "season": code}); continue
        response.raise_for_status()
        for match in parse_csv(response.text, competition, f"{start_year}/{start_year + 1}"):
            connection.execute("""INSERT INTO matches_v2(competition,season,kickoff,home_team,away_team,home_goals,away_goals,home_shots,away_shots,home_sot,away_sot,home_corners,away_corners,home_fouls,away_fouls,home_yellows,away_yellows,home_reds,away_reds,referee,completed)
            VALUES(:competition,:season,:kickoff,:home_team,:away_team,:home_goals,:away_goals,:home_shots,:away_shots,:home_sot,:away_sot,:home_corners,:away_corners,:home_fouls,:away_fouls,:home_yellows,:away_yellows,:home_reds,:away_reds,:referee,:completed)
            ON CONFLICT(competition,kickoff,home_team,away_team) DO UPDATE SET home_goals=excluded.home_goals, away_goals=excluded.away_goals, completed=excluded.completed""", match)
            imported += 1
    connection.commit(); return imported

def promote_unplayed_matches_to_fixtures(connection) -> int:
    rows = connection.execute("SELECT competition,kickoff,home_team,away_team FROM matches_v2 WHERE completed=0").fetchall()
    for row in rows:
        identity = "|".join(row)
        connection.execute("""INSERT INTO fixtures(external_fixture_id,competition,kickoff,home_team,away_team,status)
        VALUES(?,?,?,?,?,?) ON CONFLICT(external_fixture_id) DO NOTHING""", (identity, *row, "scheduled"))
    connection.commit(); return len(rows)
