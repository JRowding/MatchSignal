from .config import CONFIG, MODEL_VERSION
from .features import chronological_elo, team_form
from .poisson import markets, score_matrix

def expected_goals(matches, competition: str, home_team: str, away_team: str, kickoff):
    prior = [match for match in matches if match["competition"] == competition and match["kickoff"] < kickoff.isoformat()]
    if not prior: return 1.35, 1.05, {"reason": "league baseline only", "sample": 0}
    league_goals = sum(match["home_goals"] + match["away_goals"] for match in prior) / (2 * len(prior))
    home = team_form(prior, home_team, kickoff, True); away = team_form(prior, away_team, kickoff, False)
    elo = chronological_elo(prior)
    home_attack = home["goals_for"] if home["goals_for"] is not None else league_goals
    home_defence = home["goals_against"] if home["goals_against"] is not None else league_goals
    away_attack = away["goals_for"] if away["goals_for"] is not None else league_goals
    away_defence = away["goals_against"] if away["goals_against"] is not None else league_goals
    elo_delta = max(-.15, min(.15, (elo.get(home_team, 1500) - elo.get(away_team, 1500)) / 2000))
    home_xg = max(.2, league_goals * (home_attack / league_goals) ** .5 * (away_defence / league_goals) ** .5 * CONFIG.home_advantage * (1 + elo_delta))
    away_xg = max(.2, league_goals * (away_attack / league_goals) ** .5 * (home_defence / league_goals) ** .5 / CONFIG.home_advantage * (1 - elo_delta))
    sample = min(home["sample"], away["sample"])
    return home_xg, away_xg, {"sample": sample, "home_form": home, "away_form": away, "elo_delta": elo_delta}

def predict(matches, competition, home_team, away_team, kickoff):
    home_xg, away_xg, evidence = expected_goals(matches, competition, home_team, away_team, kickoff)
    probabilities = markets(score_matrix(home_xg, away_xg, CONFIG.poisson_max_goals))
    confidence = "VERY HIGH" if evidence["sample"] >= 10 else "HIGH" if evidence["sample"] >= 7 else "MEDIUM" if evidence["sample"] >= 4 else "LOW"
    return {"model_version": MODEL_VERSION, "home_xg": home_xg, "away_xg": away_xg, "probabilities": probabilities, "confidence": confidence, "evidence": evidence}
