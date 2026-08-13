from collections import defaultdict
from datetime import datetime
from math import exp

from .config import CONFIG

def parse_date(value: str) -> datetime:
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try: return datetime.strptime(value[:19], pattern)
        except ValueError: pass
    raise ValueError(f"Unsupported date: {value}")

def recency_weight(kickoff: datetime, match_date: datetime, half_life_days: int = 90) -> float:
    return exp(-0.69314718056 * max((kickoff - match_date).days, 0) / half_life_days)

def team_form(matches, team: str, kickoff: datetime, home_only: bool) -> dict:
    eligible = [match for match in matches if parse_date(match["kickoff"]) < kickoff and ((match["home_team"] == team) if home_only else (match["away_team"] == team))]
    eligible = sorted(eligible, key=lambda match: parse_date(match["kickoff"]), reverse=True)[:CONFIG.recent_window]
    if not eligible: return {"sample": 0, "points_per_game": None, "goals_for": None, "goals_against": None}
    weighted = defaultdict(float); weights = 0.0
    for match in eligible:
        weight = recency_weight(kickoff, parse_date(match["kickoff"])); weights += weight
        goals_for, goals_against = (match["home_goals"], match["away_goals"]) if home_only else (match["away_goals"], match["home_goals"])
        weighted["goals_for"] += goals_for * weight; weighted["goals_against"] += goals_against * weight
        weighted["points"] += (3 if goals_for > goals_against else 1 if goals_for == goals_against else 0) * weight
    return {"sample": len(eligible), "points_per_game": weighted["points"] / weights, "goals_for": weighted["goals_for"] / weights, "goals_against": weighted["goals_against"] / weights}

def chronological_elo(matches, initial: float = 1500.0, k: float = CONFIG.elo_k) -> dict:
    ratings = defaultdict(lambda: initial)
    for match in sorted(matches, key=lambda item: parse_date(item["kickoff"])):
        home, away = match["home_team"], match["away_team"]
        expected_home = 1 / (1 + 10 ** ((ratings[away] - ratings[home]) / 400))
        actual_home = 1 if match["home_goals"] > match["away_goals"] else .5 if match["home_goals"] == match["away_goals"] else 0
        delta = k * (actual_home - expected_home)
        ratings[home] += delta; ratings[away] -= delta
    return dict(ratings)
