"""Independent, data-gated count models for match statistics."""
from collections import defaultdict
from math import floor, sqrt

from .config import CONFIG, SUPPORTED_COMPETITIONS
from .features import parse_date, recency_weight
from .poisson import poisson_probability

MARKETS = {
    "shots": ("shots", (16.5, 18.5, 20.5), (7.5, 8.5, 9.5)),
    "shots_on_target": ("shots_on_target", (4.5, 5.5, 6.5), (1.5, 2.5, 3.5)),
    "corners": ("corners", (6.5, 7.5, 8.5, 9.5), (2.5, 3.5, 4.5)),
    "fouls": ("fouls", (18.5, 20.5, 22.5), (7.5, 8.5, 9.5)),
    "cards": ("cards", (1.5, 2.5, 3.5, 4.5), (.5, 1.5, 2.5)),
}
FIELD_MAP = {
    "shots": ("home_shots", "away_shots"), "shots_on_target": ("home_sot", "away_sot"),
    "corners": ("home_corners", "away_corners"), "fouls": ("home_fouls", "away_fouls"),
}

def _value(match, metric, home):
    prefix = "home" if home else "away"
    if metric == "cards":
        yellow, red = match.get(f"{prefix}_yellows"), match.get(f"{prefix}_reds")
        return None if yellow is None or red is None else yellow + red
    return match.get(FIELD_MAP[metric][0 if home else 1])

def _form(matches, team, kickoff, home_only, metric):
    eligible = []
    for match in matches:
        if parse_date(match["kickoff"]) >= kickoff or (match["home_team"] == team) != home_only:
            continue
        own, against = _value(match, metric, home_only), _value(match, metric, not home_only)
        if own is not None and against is not None:
            eligible.append((match, own, against))
    eligible.sort(key=lambda row: parse_date(row[0]["kickoff"]), reverse=True)
    eligible = eligible[:CONFIG.recent_window]
    if not eligible: return {"sample": 0, "for": None, "against": None}
    totals, weight_total = defaultdict(float), 0.0
    for match, own, against in eligible:
        weight = recency_weight(kickoff, parse_date(match["kickoff"])); weight_total += weight
        totals["for"] += own * weight; totals["against"] += against * weight
    return {"sample": len(eligible), "for": totals["for"] / weight_total, "against": totals["against"] / weight_total}

def _tail(mean, threshold):
    return max(0.0, min(1.0, 1 - sum(poisson_probability(value, mean) for value in range(floor(threshold) + 1))))

def predict_count_markets(matches, competition, home_team, away_team, kickoff):
    """Model statistics independently and omit any market with weak support."""
    english = [m for m in matches if m["competition"] in SUPPORTED_COMPETITIONS.values() and parse_date(m["kickoff"]) < kickoff]
    league = [m for m in english if m["competition"] == competition]
    if not league: return {}, {}
    probabilities, evidence = {}, {}
    for metric, (label, thresholds, team_thresholds) in MARKETS.items():
        usable = [(_value(m, metric, True), _value(m, metric, False)) for m in league]
        usable = [(home, away) for home, away in usable if home is not None and away is not None]
        if len(usable) < 20: continue
        baseline = sum(home + away for home, away in usable) / (2 * len(usable))
        home = _form(english, home_team, kickoff, True, metric)
        away = _form(english, away_team, kickoff, False, metric)
        if min(home["sample"], away["sample"]) < CONFIG.min_sample: continue
        home_mean = .75 * sqrt(home["for"] * away["against"]) + .25 * baseline
        away_mean = .75 * sqrt(away["for"] * home["against"]) + .25 * baseline
        for threshold in thresholds: probabilities[f"{label}_over_{threshold}"] = _tail(home_mean + away_mean, threshold)
        for side, mean in (("home", home_mean), ("away", away_mean)):
            for threshold in team_thresholds:
                probabilities[f"{side}_{label}_over_{threshold}"] = _tail(mean, threshold)
        evidence[metric] = {"sample": min(home["sample"], away["sample"]), "league_sample": len(usable), "home_expected": home_mean, "away_expected": away_mean}
    return probabilities, evidence
