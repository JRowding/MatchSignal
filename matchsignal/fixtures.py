"""Free fixture providers for the English football pyramid."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging

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
    BASE = "https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php"
    LEAGUES = {
        "4328": "Premier League", "4329": "Championship",
        "4396": "League One", "4397": "League Two", "4590": "National League",
    }

    def __init__(self, session=requests):
        self.session = session

    def upcoming(self) -> list[Fixture]:
        fixtures = []
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cutoff = now + timedelta(days=CONFIG.fixture_lookahead_days)
        for league_id, competition in self.LEAGUES.items():
            try:
                response = self.session.get(self.BASE, params={"id": league_id}, timeout=30,
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

def upsert_fixtures(connection, fixtures: list[Fixture]) -> int:
    for fixture in fixtures:
        connection.execute("""INSERT INTO fixtures(external_fixture_id,competition,kickoff,home_team,away_team,status)
        VALUES(?,?,?,?,?,?) ON CONFLICT(external_fixture_id) DO UPDATE SET kickoff=excluded.kickoff,status=excluded.status""",
        (fixture.external_fixture_id, fixture.competition, fixture.kickoff, fixture.home_team, fixture.away_team, fixture.status))
    connection.commit(); return len(fixtures)
