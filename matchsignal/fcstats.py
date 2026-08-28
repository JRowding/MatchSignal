"""FCStats enrichment for current-season completed scores."""
from datetime import datetime
from html import unescape
import logging
import re
from time import sleep

import requests

from .normalization import canonical_team

LOG = logging.getLogger(__name__)

BASE = "https://fcstats.com"
LEAGUES = {
    "Premier League": "league,premier-league-england,1.php",
    "Championship": "league,championship-england,2.php",
    "League One": "league,league-one-england,3.php",
    "League Two": "league,league-two-england,4.php",
    "National League": "league,national-league-england,5.php",
}


def _clean(value):
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _date(value):
    for pattern in ("%d.%m.%Y", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), pattern).date().isoformat()
        except ValueError:
            pass
    return None


def parse_league_page(content: str, competition: str, season: str) -> list[dict]:
    rows = []
    for row in re.findall(r'<tr[^>]*class="matchRow[^"]*"[^>]*>.*?</tr>', content, flags=re.DOTALL):
        date = _cell_text(row, "matchDate")
        home = _team_text(row, "teamHomeName")
        away = _team_text(row, "teamAwayName")
        score_match = re.search(r'<td[^>]*class="[^"]*matchResult[^"]*"[^>]*>.*?>(\d+:\d+)</a>', row, flags=re.DOTALL)
        if not date or not home or not away or not score_match:
            continue
        kickoff = _date(date)
        if not kickoff:
            continue
        home_goals, away_goals = [int(part) for part in score_match.group(1).split(":")]
        rows.append({
            "competition": competition,
            "season": season,
            "kickoff": kickoff,
            "home_team": canonical_team(home),
            "away_team": canonical_team(away),
            "home_goals": home_goals,
            "away_goals": away_goals,
            "home_shots": None, "away_shots": None,
            "home_sot": None, "away_sot": None,
            "home_corners": None, "away_corners": None,
            "home_fouls": None, "away_fouls": None,
            "home_yellows": None, "away_yellows": None,
            "home_reds": None, "away_reds": None,
            "referee": None,
            "completed": 1,
        })
    return rows


def _cell_text(row, class_name):
    match = re.search(rf'<td[^>]*class="[^"]*{class_name}[^"]*"[^>]*>(.*?)</td>', row, flags=re.DOTALL)
    if not match:
        return None
    text = re.sub(r"<[^>]+>", " ", match.group(1))
    return _clean(text)


def _team_text(row, class_name):
    match = re.search(rf'<td[^>]*class="[^"]*{class_name}[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>', row, flags=re.DOTALL)
    return _clean(match.group(1)) if match else None


def import_current_scores(connection, session=requests) -> int:
    current = datetime.now().year
    season = f"{current}/{current + 1}" if datetime.now().month >= 7 else f"{current - 1}/{current}"
    imported = 0
    for competition, path in LEAGUES.items():
        try:
            response = _get(session, f"{BASE}/{path}")
        except requests.RequestException as exc:
            LOG.warning("FCStats unavailable for %s: %s", competition, exc)
            continue
        for match in parse_league_page(response.text, competition, season):
            connection.execute("""INSERT INTO matches_v2(competition,season,kickoff,home_team,away_team,home_goals,away_goals,home_shots,away_shots,home_sot,away_sot,home_corners,away_corners,home_fouls,away_fouls,home_yellows,away_yellows,home_reds,away_reds,referee,completed)
            VALUES(:competition,:season,:kickoff,:home_team,:away_team,:home_goals,:away_goals,:home_shots,:away_shots,:home_sot,:away_sot,:home_corners,:away_corners,:home_fouls,:away_fouls,:home_yellows,:away_yellows,:home_reds,:away_reds,:referee,:completed)
            ON CONFLICT(competition,kickoff,home_team,away_team) DO UPDATE SET home_goals=excluded.home_goals, away_goals=excluded.away_goals, completed=excluded.completed""", match)
            imported += 1
        sleep(1)
    connection.commit()
    return imported


def _get(session, url):
    last_error = None
    for _ in range(3):
        try:
            response = session.get(url, timeout=30, headers={"User-Agent": "MatchSignal/2.5"})
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            sleep(2)
    raise last_error
