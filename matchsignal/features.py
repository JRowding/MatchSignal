from collections import defaultdict
from datetime import datetime
from math import exp

from .config import COMPETITION_ELO_PRIORS, CONFIG

def parse_date(value: str) -> datetime:
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try: return datetime.strptime(value[:19], pattern)
        except ValueError: pass
    raise ValueError(f"Unsupported date: {value}")

def recency_weight(kickoff: datetime, match_date: datetime, half_life_days: int = 90) -> float:
    return exp(-0.69314718056 * max((kickoff - match_date).days, 0) / half_life_days)

def team_form(matches, team: str, kickoff: datetime, home_only: bool | None) -> dict:
    def matches_team(match):
        if home_only is True:
            return match["home_team"] == team
        if home_only is False:
            return match["away_team"] == team
        return match["home_team"] == team or match["away_team"] == team

    eligible = [match for match in matches if parse_date(match["kickoff"]) < kickoff and matches_team(match)]
    eligible = sorted(eligible, key=lambda match: parse_date(match["kickoff"]), reverse=True)[:CONFIG.recent_window]
    if not eligible: return {"sample": 0, "points_per_game": None, "goals_for": None, "goals_against": None}
    weighted = defaultdict(float); weights = 0.0
    for match in eligible:
        weight = recency_weight(kickoff, parse_date(match["kickoff"])); weights += weight
        if match["home_team"] == team:
            goals_for, goals_against = match["home_goals"], match["away_goals"]
        else:
            goals_for, goals_against = match["away_goals"], match["home_goals"]
        weighted["goals_for"] += goals_for * weight; weighted["goals_against"] += goals_against * weight
        weighted["points"] += (3 if goals_for > goals_against else 1 if goals_for == goals_against else 0) * weight
    return {"sample": len(eligible), "points_per_game": weighted["points"] / weights, "goals_for": weighted["goals_for"] / weights, "goals_against": weighted["goals_against"] / weights}

def league_table(matches, competition: str, kickoff: datetime) -> dict:
    eligible = [match for match in matches if match["competition"] == competition and parse_date(match["kickoff"]) < kickoff]
    if not eligible:
        return {}
    latest_season = max(match.get("season", "") for match in eligible)
    season_matches = [match for match in eligible if match.get("season", "") == latest_season]
    table = defaultdict(lambda: {"played": 0, "points": 0, "goals_for": 0, "goals_against": 0})
    for match in season_matches:
        home, away = match["home_team"], match["away_team"]
        home_goals, away_goals = match["home_goals"], match["away_goals"]
        table[home]["played"] += 1; table[away]["played"] += 1
        table[home]["goals_for"] += home_goals; table[home]["goals_against"] += away_goals
        table[away]["goals_for"] += away_goals; table[away]["goals_against"] += home_goals
        if home_goals > away_goals:
            table[home]["points"] += 3
        elif away_goals > home_goals:
            table[away]["points"] += 3
        else:
            table[home]["points"] += 1; table[away]["points"] += 1
    ordered = sorted(table.items(), key=lambda item: (
        -item[1]["points"],
        -(item[1]["goals_for"] - item[1]["goals_against"]),
        -item[1]["goals_for"],
        item[0],
    ))
    team_count = len(ordered)
    return {
        team: {
            **record,
            "position": index + 1,
            "team_count": team_count,
            "goal_difference": record["goals_for"] - record["goals_against"],
            "points_per_game": record["points"] / record["played"] if record["played"] else 0,
        }
        for index, (team, record) in enumerate(ordered)
    }

def chronological_elo(matches, initial: float = 1500.0, k: float = CONFIG.elo_k) -> dict:
    # A team keeps its earned rating when it moves division.
    ratings = {}
    for match in sorted(matches, key=lambda item: parse_date(item["kickoff"])):
        home, away = match["home_team"], match["away_team"]
        tier_prior = COMPETITION_ELO_PRIORS.get(match.get("competition"), initial)
        ratings.setdefault(home, tier_prior)
        ratings.setdefault(away, tier_prior)
        expected_home = 1 / (1 + 10 ** ((ratings[away] - ratings[home]) / 400))
        actual_home = 1 if match["home_goals"] > match["away_goals"] else .5 if match["home_goals"] == match["away_goals"] else 0
        delta = k * (actual_home - expected_home)
        ratings[home] += delta; ratings[away] -= delta
    return dict(ratings)
