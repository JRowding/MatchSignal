"""Fixture-provider boundary. Providers return only upcoming fixtures."""
from dataclasses import dataclass
from datetime import datetime

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

def upsert_fixtures(connection, fixtures: list[Fixture]) -> int:
    for fixture in fixtures:
        connection.execute("""INSERT INTO fixtures(external_fixture_id,competition,kickoff,home_team,away_team,status)
        VALUES(?,?,?,?,?,?) ON CONFLICT(external_fixture_id) DO UPDATE SET kickoff=excluded.kickoff,status=excluded.status""",
        (fixture.external_fixture_id, fixture.competition, fixture.kickoff, fixture.home_team, fixture.away_team, fixture.status))
    connection.commit(); return len(fixtures)
