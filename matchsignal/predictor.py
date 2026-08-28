from .config import CONFIG, MODEL_VERSION, SUPPORTED_COMPETITIONS
from .count_models import predict_count_markets
from .features import chronological_elo, league_table, team_form
from .poisson import markets, score_matrix

def expected_goals(matches, competition: str, home_team: str, away_team: str, kickoff):
    # Use a shared English-pyramid sample for team form and Elo.  The fixture
    # division remains the local goal baseline, so a cup tie is still valid.
    english = [match for match in matches if match["competition"] in SUPPORTED_COMPETITIONS.values() and match["kickoff"] < kickoff.isoformat()]
    prior = [match for match in english if match["competition"] == competition]
    if not prior:
        prior = english
    if not prior: return 1.35, 1.05, {"reason": "league baseline only", "sample": 0}
    league_goals = sum(match["home_goals"] + match["away_goals"] for match in prior) / (2 * len(prior))
    home = team_form(english, home_team, kickoff, True); away = team_form(english, away_team, kickoff, False)
    home_any = team_form(english, home_team, kickoff, None); away_any = team_form(english, away_team, kickoff, None)
    elo = chronological_elo(english)
    table = league_table(english, competition, kickoff)
    home_attack = home["goals_for"] if home["goals_for"] is not None else home_any["goals_for"] if home_any["goals_for"] is not None else league_goals
    home_defence = home["goals_against"] if home["goals_against"] is not None else home_any["goals_against"] if home_any["goals_against"] is not None else league_goals
    away_attack = away["goals_for"] if away["goals_for"] is not None else away_any["goals_for"] if away_any["goals_for"] is not None else league_goals
    away_defence = away["goals_against"] if away["goals_against"] is not None else away_any["goals_against"] if away_any["goals_against"] is not None else league_goals
    elo_delta = max(-.15, min(.15, (elo.get(home_team, 1500) - elo.get(away_team, 1500)) / 2000))
    table_delta = 0.0
    if home_team in table and away_team in table:
        team_count = max(table[home_team]["team_count"] - 1, 1)
        position_delta = (table[away_team]["position"] - table[home_team]["position"]) / team_count
        ppg_delta = (table[home_team]["points_per_game"] - table[away_team]["points_per_game"]) / 3
        table_delta = max(-.12, min(.12, (position_delta * .08) + (ppg_delta * .08)))
    strength_delta = max(-.22, min(.22, elo_delta + table_delta))
    home_xg = max(.2, league_goals * (home_attack / league_goals) ** .5 * (away_defence / league_goals) ** .5 * CONFIG.home_advantage * (1 + strength_delta))
    away_xg = max(.2, league_goals * (away_attack / league_goals) ** .5 * (home_defence / league_goals) ** .5 / CONFIG.home_advantage * (1 - strength_delta))
    sample = min(home["sample"], away["sample"])
    return home_xg, away_xg, {
        "sample": max(sample, min(home_any["sample"], away_any["sample"])),
        "home_form": home, "away_form": away,
        "home_any_form": home_any, "away_any_form": away_any,
        "elo_delta": elo_delta, "table_delta": table_delta,
        "table": {"home": table.get(home_team), "away": table.get(away_team)}
    }

def predict(matches, competition, home_team, away_team, kickoff):
    home_xg, away_xg, evidence = expected_goals(matches, competition, home_team, away_team, kickoff)
    probabilities = markets(score_matrix(home_xg, away_xg, CONFIG.poisson_max_goals))
    confidence = "VERY HIGH" if evidence["sample"] >= 10 else "HIGH" if evidence["sample"] >= 7 else "MEDIUM" if evidence["sample"] >= 4 else "LOW"
    count_probabilities, count_evidence = predict_count_markets(matches, competition, home_team, away_team, kickoff)
    probabilities.update(count_probabilities)
    evidence["count_models"] = count_evidence
    return {"model_version": MODEL_VERSION, "home_xg": home_xg, "away_xg": away_xg, "probabilities": probabilities, "confidence": confidence, "evidence": evidence}
