"""Free fixture providers for the English football pyramid."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
import json
import logging
import re

import requests

from .normalization import canonical_team
from .config import CONFIG

LOG = logging.getLogger(__name__)

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
        "National League": "National League",
    }
    SKY_DAILY_URL = "https://www.skysports.com/football-scores-fixtures/{date}"

    def __init__(self, session=requests):
        self.session = session

    def upcoming(self) -> list[Fixture]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cutoff = now + timedelta(days=CONFIG.fixture_lookahead_days)
        fixtures = self._sky_fixtures(now, cutoff)
        if fixtures:
            return fixtures

        fixtures = []
        season_start = now.year if now.month >= 7 else now.year - 1
        season = f"{season_start}-{season_start + 1}"
        for league_id, competition in self.LEAGUES.items():
            try:
                response = self.session.get(self.BASE, params={"id": league_id, "s": season}, timeout=30,
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
                if not now <= kickoff_at <= cutoff:
                    continue
                kickoff = kickoff_at.isoformat()
                fixtures.append(Fixture(str(event["idEvent"]), competition, kickoff,
                                        canonical_team(home), canonical_team(away)))
        return fixtures

    def _sky_fixtures(self, now, cutoff):
        """Sky's dated pages cover all supported English tiers without API keys."""
        fixtures = []
        current = now.date()
        while current <= cutoff.date():
            try:
                response = self.session.get(self.SKY_DAILY_URL.format(date=current.isoformat()), timeout=30,
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
