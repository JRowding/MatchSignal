import re
import unicodedata

ALIASES = {
    "man city": "Manchester City", "brighton": "Brighton and Hove Albion",
    "newcastle": "Newcastle United", "nott'm forest": "Nottingham Forest",
    "tottenham": "Tottenham Hotspur", "west ham": "West Ham United",
    "leeds": "Leeds United", "qpr": "Queens Park Rangers",
    "norwich": "Norwich City", "leicester": "Leicester City",
    "hull": "Hull City", "cardiff": "Cardiff City", "swansea": "Swansea City",
    "birmingham": "Birmingham City", "ipswich": "Ipswich Town",
    "oxford": "Oxford United", "stoke": "Stoke City", "coventry": "Coventry City",
    "preston": "Preston North End", "sheffield weds": "Sheffield Wednesday",
    "west bromwich": "West Bromwich Albion",
    "derby": "Derby County", "bolton": "Bolton Wanderers", "charlton": "Charlton Athletic",
    "luton": "Luton Town", "plymouth": "Plymouth Argyle", "peterboro": "Peterborough United",
    "wycombe": "Wycombe Wanderers", "doncaster": "Doncaster Rovers", "bradford": "Bradford City",
    "exeter": "Exeter City", "northampton": "Northampton Town", "lincoln": "Lincoln City",
    "rotherham": "Rotherham United", "mansfield": "Mansfield Town", "wigan": "Wigan Athletic",
    "huddersfield": "Huddersfield Town", "burton": "Burton Albion", "stockport": "Stockport County",
    "cambridge": "Cambridge United", "bristol rvs": "Bristol Rovers", "cheltenham": "Cheltenham Town",
    "colchester": "Colchester United", "grimsby": "Grimsby Town", "mk dons": "Milton Keynes Dons",
    "notts county": "Notts County", "swindon": "Swindon Town", "shrewsbury": "Shrewsbury Town",
    "tranmere": "Tranmere Rovers", "salford": "Salford City", "harrogate": "Harrogate Town",
    "crewe": "Crewe Alexandra", "barrow": "Barrow", "barnet": "Barnet",
    "hartlepool": "Hartlepool United", "kidderminster": "Kidderminster Harriers",
    "york": "York City", "halifax": "FC Halifax Town", "dagenham": "Dagenham and Redbridge",
    "forest green": "Forest Green Rovers", "sutton": "Sutton United", "southend": "Southend United",
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
