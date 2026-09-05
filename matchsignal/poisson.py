from math import exp, factorial
from typing import Dict, Tuple

def poisson_probability(goals: int, mean: float) -> float:
    if mean < 0:
        raise ValueError("Expected goals cannot be negative")
    return exp(-mean) * mean ** goals / factorial(goals)

def score_matrix(home_xg: float, away_xg: float, max_goals: int = 8) -> Dict[Tuple[int, int], float]:
    matrix = {(home, away): poisson_probability(home, home_xg) * poisson_probability(away, away_xg)
              for home in range(max_goals + 1) for away in range(max_goals + 1)}
    total = sum(matrix.values())
    return {score: probability / total for score, probability in matrix.items()}

def markets(matrix: Dict[Tuple[int, int], float]) -> dict[str, float]:
    result = {"home_win": 0.0, "draw": 0.0, "away_win": 0.0,
              "home_win_btts": 0.0, "away_win_btts": 0.0}
    for (home, away), probability in matrix.items():
        result_market = "home_win" if home > away else "away_win" if away > home else "draw"
        result[result_market] += probability
        total = home + away
        for threshold in (0.5, 1.5, 2.5, 3.5):
            result[f"over_{threshold}"] = result.get(f"over_{threshold}", 0.0) + (probability if total > threshold else 0.0)
        both_score = home > 0 and away > 0
        result["btts_yes"] = result.get("btts_yes", 0.0) + (probability if both_score else 0.0)
        if both_score and home > away:
            result["home_win_btts"] += probability
        elif both_score and away > home:
            result["away_win_btts"] += probability
        for side, goals in (("home", home), ("away", away)):
            for threshold in (0.5, 1.5, 2.5):
                result[f"{side}_over_{threshold}"] = result.get(f"{side}_over_{threshold}", 0.0) + (probability if goals > threshold else 0.0)
    result["btts_no"] = 1 - result["btts_yes"]
    result["home_or_draw"] = result["home_win"] + result["draw"]
    result["away_or_draw"] = result["away_win"] + result["draw"]
    result["home_or_away"] = result["home_win"] + result["away_win"]
    return result
