"""Free fixture providers for the English football pyramid."""
from dataclasses import dataclass
from datetime import datetime, time as datetime_time, timedelta
from html import unescape
import json
import logging
import re

import requests

from .normalization import canonical_team
from .config import CONFIG

LOG = logging.getLogger(__name__)


def fixture_window(now):
    return (
        datetime.combine(now.date(), datetime_time.min),
        datetime.combine(
            now.date() + timedelta(days=CONFIG.fixture_lookahead_days), datetime_time.max
        ),
    )

@dataclass(frozen=True)
class Fixture:
    external_fixture_id: str
    competition: str
    kickoff: str
    home_team: str
    away_team: str
    status: str = "scheduled"

class FixtureProvider:
    def upcoming(self) -> list[Fixture]:
        raise NotImplementedError


class TheSportsDBProvider(FixtureProvider):
    """Public, keyless fixture source covering all five supported tiers."""
    BASE = "https://www.thesportsdb.com/api/v1/json/123/eventsseason.php"
    LEAGUES = {
        "4328": "Premier League", "4329": "Championship",
        "4396": "League One", "4397": "League Two",
    }
    SKY_COMPETITIONS = {
        "Premier League": "Premier League",
        "Sky Bet Championship": "Championship",
        "Sky Bet League One": "League One",
        "Sky Bet League Two": "League Two",
    }
    SKY_DAILY_URL = "https://www.skysports.com/football-scores-fixtures/{date}"
    FWP_NATIONAL_LEAGUE_URL = "https://www.footballwebpages.co.uk/fixtures-results/national-league"

    def __init__(self, session=requests):
        self.session = session

    def upcoming(self) -> list[Fixture]:
        now = datetime.now()
        window_start, window_end = fixture_window(now)
        fixtures = self._sky_fixtures(window_start, window_end)
        fixtures.extend(self._football_web_pages_national_league(window_start, window_end))
        if fixtures:
            return fixtures

        fixtures = []
        season_start = now.year if now.month >= 7 else now.year - 1
        season = f"{season_start}-{season_start + 1}"
        for league_id, competition in self.LEAGUES.items():
            try:
                response = self.session.get(self.BASE, params={"id": league_id, "s": season}, timeout=CONFIG.source_timeout_seconds,
                                            headers={"User-Agent": "MatchSignal/2.0"})
                response.raise_for_status()
            except requests.RequestException as exc:
                # Preserve previously saved fixtures when a free upstream is
                # temporarily rate-limited instead of aborting the whole run.
                LOG.warning("Fixture provider unavailable for %s: %s", competition, exc)
                continue
            for event in response.json().get("events") or []:
                home, away = event.get("strHomeTeam"), event.get("strAwayTeam")
                date, time = event.get("dateEvent"), event.get("strTime") or "00:00:00"
                if not event.get("idEvent") or not home or not away or not date:
                    continue
                try:
                    kickoff_at = datetime.fromisoformat(f"{date}T{time[:8]}")
                except ValueError:
                    kickoff_at = datetime.fromisoformat(f"{date}T00:00:00")
                if not window_start <= kickoff_at <= window_end:
                    continue
                kickoff = kickoff_at.isoformat()
                fixtures.append(Fixture(str(event["idEvent"]), competition, kickoff,
                                        canonical_team(home), canonical_team(away)))
        return fixtures

    def _football_web_pages_national_league(self, now, cutoff):
        fixtures = []
        months = {(now.year, now.month), (cutoff.year, cutoff.month)}
        for year, month in sorted(months):
            try:
                response = self.session.get(self.FWP_NATIONAL_LEAGUE_URL, params={"month": month}, timeout=CONFIG.source_timeout_seconds,
                                            headers={"User-Agent": "MatchSignal/2.3"})
                response.raise_for_status()
            except requests.RequestException as exc:
                LOG.warning("Football Web Pages National League fixtures unavailable for %s/%s: %s", month, year, exc)
                continue
            rows = re.findall(
                r'<tr[^>]+data-href="match/([^"]+)"[^>]*>.*?'
                r'<td class="d-none export-only">([^<]+)</td>.*?'
                r'<td class="status"[^>]*>([^<]+)</td>.*?'
                r'<td class="team home-team"[^>]*data-export="([^"]+)".*?'
                r'<td class="team away-team"[^>]*data-export="([^"]+)"',
                response.text,
                flags=re.DOTALL,
            )
            for path, date_text, time_text, home, away in rows:
                try:
                    kickoff = self._football_web_pages_kickoff(date_text, time_text)
                except ValueError:
                    continue
                if not now <= kickoff <= cutoff:
                    continue
                fixtures.append(Fixture(f"fwp-{path}", "National League", kickoff.isoformat(),
                                        canonical_team(unescape(home)), canonical_team(unescape(away))))
        return fixtures

    @staticmethod
    def _football_web_pages_kickoff(date_text, time_text):
        match_date = datetime.strptime(date_text.strip(), "%d/%m/%Y")
        text = time_text.strip().lower().replace(".", ":")
        match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", text)
        if not match:
            raise ValueError(f"Unsupported fixture time: {time_text}")
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if match.group(3) == "pm" and hour != 12:
            hour += 12
        if match.group(3) == "am" and hour == 12:
            hour = 0
        return match_date.replace(hour=hour, minute=minute)

    def _sky_fixtures(self, now, cutoff):
        """Sky's dated pages cover all supported English tiers without API keys."""
        fixtures = []
        current = now.date()
        while current <= cutoff.date():
            try:
                response = self.session.get(self.SKY_DAILY_URL.format(date=current.isoformat()), timeout=CONFIG.source_timeout_seconds,
                                            headers={"User-Agent": "MatchSignal/2.2"})
                response.raise_for_status()
            except requests.RequestException as exc:
                LOG.warning("Sky fixture page unavailable for %s: %s", current, exc)
                current += timedelta(days=1); continue
            for raw in re.findall(r'data-state="([^"]+)"', response.text):
                try:
                    event = json.loads(unescape(raw))
                    source_competition = event["competition"]["name"]["full"]
                    competition = self.SKY_COMPETITIONS.get(source_competition)
                    if not competition or not event.get("isFixture"):
                        continue
                    time = event["start"].get("time") or "00:00"
                    kickoff = datetime.fromisoformat(f"{current.isoformat()}T{time}:00")
                    if not now <= kickoff <= cutoff:
                        continue
                    home, away = event["teams"]["home"]["name"]["full"], event["teams"]["away"]["name"]["full"]
                    fixtures.append(Fixture(f"sky-{event['id']}", competition, kickoff.isoformat(),
                                            canonical_team(home), canonical_team(away)))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
            current += timedelta(days=1)
        return fixtures

def upsert_fixtures(connection, fixtures: list[Fixture]) -> int:
    for fixture in fixtures:
        connection.execute("""INSERT INTO fixtures(external_fixture_id,competition,kickoff,home_team,away_team,status)
        VALUES(?,?,?,?,?,?) ON CONFLICT(external_fixture_id) DO UPDATE SET kickoff=excluded.kickoff,status=excluded.status""",
        (fixture.external_fixture_id, fixture.competition, fixture.kickoff, fixture.home_team, fixture.away_team, fixture.status))
    connection.commit(); return len(fixtures)
