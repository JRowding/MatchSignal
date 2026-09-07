"""Robust Football-Data.co.uk CSV import for the supported English leagues."""
import csv
import io
import logging
from datetime import datetime
from time import sleep

import requests

from .config import CONFIG
from .config import SUPPORTED_COMPETITIONS
from .normalization import canonical_team
from .persistence import record_result
from .timeutils import utc_text

LOG = logging.getLogger(__name__)
BASE = "https://www.football-data.co.uk/mmz4281"


def _fetch_csv(session, relative_path):
    """Retry transient failures and the publisher's alternate HTTPS hostname."""
    last_error = None
    bases = (BASE, BASE.replace('://www.', '://'))
    for base in bases:
        for attempt in range(CONFIG.source_retries + 1):
            try:
                response = session.get(f'{base}/{relative_path}', timeout=CONFIG.source_timeout_seconds,
                                       headers={'User-Agent': 'MatchSignal/2.5'})
                if response.status_code == 404:
                    return response
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
                if status is not None and status != 429 and status < 500:
                    raise
                if attempt < CONFIG.source_retries:
                    sleep(1 + attempt)
        LOG.warning('Transient source failure at %s; trying alternate publisher endpoint if available', base)
    raise last_error

def season_code(start_year: int) -> str:
    return f"{str(start_year)[-2:]}{str(start_year + 1)[-2:]}"

def _integer(row, field):
    value = (row.get(field) or "").strip()
    return int(value) if value.lstrip("-").isdigit() else None

def _date(value: str) -> str | None:
    for pattern in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try: return datetime.strptime(value.strip(), pattern).date().isoformat()
        except ValueError: pass
    return None

def parse_csv(content: str, competition: str, season: str) -> list[dict]:
    rows = []
    for row in csv.DictReader(io.StringIO(content.lstrip("\ufeff"))):
        home, away, kickoff = (row.get("HomeTeam") or "").strip(), (row.get("AwayTeam") or "").strip(), _date(row.get("Date") or "")
        if not home or not away or not kickoff: continue
        hg, ag = _integer(row, 'FTHG'), _integer(row, 'FTAG')
        valid_score = all(v is not None and v >= 0 for v in (hg, ag))
        expected_result = ('H' if hg > ag else 'A' if ag > hg else 'D') if valid_score else None
        if row.get('FTR') in ('H', 'D', 'A') and row['FTR'] != expected_result:
            raise ValueError(f'Contradictory full-time result: {competition} {kickoff} {home} {away}')
        result_kickoff = None
        if row.get('Time'):
            try:
                result_kickoff = utc_text(datetime.strptime(f"{kickoff} {row['Time']}", '%Y-%m-%d %H:%M'), 'Europe/London')
            except ValueError:
                LOG.warning('Invalid result kickoff time for %s %s %s', competition, home, away)
        rows.append({
            "result_kickoff": result_kickoff,
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
            "completed": int(all(v is not None and v >= 0 for v in (_integer(row, "FTHG"), _integer(row, "FTAG"))) and row.get('FTR') in ('H', 'D', 'A')),
        })
    return rows

def import_season(connection, start_year: int, session=requests) -> int:
    code = season_code(start_year); imported = 0
    for source_code, competition in SUPPORTED_COMPETITIONS.items():
        try:
            response = _fetch_csv(session, f'{code}/{source_code}.csv')
            if response.status_code == 404:
                LOG.info("Source unavailable", extra={"competition": competition, "season": code}); continue
            response.raise_for_status()
        except requests.RequestException as exc:
            LOG.warning("Football-Data unavailable for %s %s: %s", competition, code, exc)
            continue
        parsed = parse_csv(response.text, competition, f"{start_year}/{start_year + 1}")
        identities = {}
        for match in parsed:
            key = (match['kickoff'], match['home_team'], match['away_team'])
            identities.setdefault(key, []).append(match)
        for key, duplicates in identities.items():
            if len({(m['home_goals'], m['away_goals'], m['completed']) for m in duplicates}) != 1:
                raise ValueError(f'Conflicting source results for {competition} {key}')
        for match in (rows[0] for rows in identities.values()):
            record_result(connection, match, 'football-data')
            connection.execute("""INSERT INTO matches_v2(competition,season,kickoff,home_team,away_team,home_goals,away_goals,home_shots,away_shots,home_sot,away_sot,home_corners,away_corners,home_fouls,away_fouls,home_yellows,away_yellows,home_reds,away_reds,referee,completed,source)
            VALUES(:competition,:season,:kickoff,:home_team,:away_team,:home_goals,:away_goals,:home_shots,:away_shots,:home_sot,:away_sot,:home_corners,:away_corners,:home_fouls,:away_fouls,:home_yellows,:away_yellows,:home_reds,:away_reds,:referee,:completed,'football-data')
            ON CONFLICT(competition,kickoff,home_team,away_team) DO UPDATE SET
            home_goals=excluded.home_goals, away_goals=excluded.away_goals,
            home_shots=excluded.home_shots, away_shots=excluded.away_shots,
            home_sot=excluded.home_sot, away_sot=excluded.away_sot,
            home_corners=excluded.home_corners, away_corners=excluded.away_corners,
            home_fouls=excluded.home_fouls, away_fouls=excluded.away_fouls,
            home_yellows=excluded.home_yellows, away_yellows=excluded.away_yellows,
            home_reds=excluded.home_reds, away_reds=excluded.away_reds,
            referee=excluded.referee, completed=excluded.completed, source=excluded.source""", match)
            imported += 1
    connection.commit(); return imported

def promote_unplayed_matches_to_fixtures(connection) -> int:
    # Historic CSV rows have no reliable scheduled kickoff. Only timed fixture
    # providers can create eligible live predictions.
    return 0
