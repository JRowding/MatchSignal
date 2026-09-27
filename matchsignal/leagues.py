"""Single registry of supported competitions and publisher identifiers."""
from dataclasses import dataclass

@dataclass(frozen=True)
class League:
    name: str
    sky: str
    fwp: str | None = None

LEAGUES = (
    League('Premier League', 'premier-league', 'premier-league'),
    League('Championship', 'championship', 'championship'),
    League('League One', 'league-1', 'league-one'),
    League('League Two', 'league-2', 'league-two'),
    League('National League', 'national-league', 'national-league'),
    League('National League North', 'national-league-north', 'national-league-north'),
    League('National League South', 'national-league-south', 'national-league-south'),
    League('Scottish Premiership', 'scottish-premiership'),
    League('Scottish Championship', 'scottish-championship'),
    League('Scottish League One', 'scottish-league-one'),
    League('Scottish League Two', 'scottish-league-two'),
)
