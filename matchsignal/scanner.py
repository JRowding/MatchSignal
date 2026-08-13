from .config import CONFIG

LABELS = {
    "home_win": "Home win", "draw": "Draw", "away_win": "Away win", "over_0.5": "Over 0.5 goals",
    "over_1.5": "Over 1.5 goals", "over_2.5": "Over 2.5 goals", "over_3.5": "Over 3.5 goals",
    "btts_yes": "Both teams to score", "btts_no": "Both teams not to score",
    "home_over_0.5": "Home team 1+ goal", "home_over_1.5": "Home team 2+ goals",
    "away_over_0.5": "Away team 1+ goal", "away_over_1.5": "Away team 2+ goals",
}
for metric, display, thresholds in (
    ("shots", "shots", (16.5, 18.5, 20.5)), ("shots_on_target", "shots on target", (4.5, 5.5, 6.5)),
    ("corners", "corners", (6.5, 7.5, 8.5, 9.5)), ("fouls", "fouls", (18.5, 20.5, 22.5)),
    ("cards", "cards", (1.5, 2.5, 3.5, 4.5)),
):
    for threshold in thresholds: LABELS[f"{metric}_over_{threshold}"] = f"Over {threshold} {display}"
for side in ("home", "away"):
    for threshold in (2.5, 3.5, 4.5): LABELS[f"{side}_corners_over_{threshold}"] = f"{side.title()} team over {threshold} corners"
def strongest(predictions, minimum=CONFIG.scanner_min_probability, maximum=CONFIG.scanner_max_probability):
    return sorted((prediction for prediction in predictions if minimum <= prediction["probability"] <= maximum), key=lambda item: item["probability"], reverse=True)
