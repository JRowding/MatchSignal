import re
import unicodedata

ALIASES = {
    "man united": "Manchester United", "man utd": "Manchester United",
    "manchester utd": "Manchester United", "sheff utd": "Sheffield United",
    "sheff wed": "Sheffield Wednesday", "west brom": "West Bromwich Albion",
    "wolverhampton wanderers": "Wolves", "blackburn rovers": "Blackburn",
    "afc bournemouth": "Bournemouth", "birmingham city": "Birmingham City",
    "brighton hove albion": "Brighton and Hove Albion", "brighton & hove albion": "Brighton and Hove Albion",
    "burnley fc": "Burnley", "chelsea fc": "Chelsea", "everton fc": "Everton",
    "fulham fc": "Fulham", "liverpool fc": "Liverpool", "manchester city": "Manchester City",
    "newcastle united": "Newcastle United", "nottingham forest": "Nottingham Forest",
    "queens park rangers": "Queens Park Rangers", "tottenham hotspur": "Tottenham Hotspur",
    "west ham united": "West Ham United", "wrexham": "Wrexham",
}

def team_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", value)

def canonical_team(value: str) -> str:
    return ALIASES.get(value.strip().lower(), value.strip())
