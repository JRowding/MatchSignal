"""Chronological backtesting: each match is predicted using only earlier data."""
from datetime import datetime

from .metrics import brier_score, calibration, log_loss
from .predictor import predict

def run(matches: list[dict], markets=("home_win", "draw", "away_win", "over_1.5", "over_2.5", "btts_yes")):
    history, results = [], []
    for match in sorted(matches, key=lambda item: item["kickoff"]):
        kickoff = datetime.fromisoformat(match["kickoff"])
        if len(history) >= 2:
            forecast = predict(history, match["competition"], match["home_team"], match["away_team"], kickoff)
            home, away = match["home_goals"], match["away_goals"]
            outcomes = {"home_win": home > away, "draw": home == away, "away_win": away > home,
                        "over_1.5": home + away > 1.5, "over_2.5": home + away > 2.5, "btts_yes": home > 0 and away > 0}
            for market in markets:
                results.append({"market": market, "probability": forecast["probabilities"][market], "actual": int(outcomes[market]), "kickoff": match["kickoff"]})
        history.append(match)
    return results

def report(results):
    by_market = {}
    for market in {row["market"] for row in results}:
        pairs = [(row["probability"], row["actual"]) for row in results if row["market"] == market]
        by_market[market] = {"sample": len(pairs), "brier": brier_score(pairs), "log_loss": log_loss(pairs), "calibration": calibration(pairs)}
    return by_market
