import re
import unicodedata

ALIASES = {
    "man united": "Manchester United", "man utd": "Manchester United",
    "manchester utd": "Manchester United", "sheff utd": "Sheffield United",
    "sheff wed": "Sheffield Wednesday", "west brom": "West Bromwich Albion",
}

def team_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", value)

def canonical_team(value: str) -> str:
    return ALIASES.get(value.strip().lower(), value.strip())
