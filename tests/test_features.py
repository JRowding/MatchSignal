from datetime import datetime
from matchsignal.features import league_table, team_form

def test_form_does_not_use_future_matches():
    matches = [
        {"kickoff":"2025-01-01", "home_team":"A", "away_team":"B", "home_goals":1, "away_goals":0},
        {"kickoff":"2025-02-01", "home_team":"A", "away_team":"B", "home_goals":9, "away_goals":0},
    ]
    form = team_form(matches, "A", datetime(2025, 1, 15), True)
    assert form["sample"] == 1
    assert form["goals_for"] == 1

def test_form_can_fall_back_to_all_venues():
    matches = [
        {"kickoff":"2025-01-01", "home_team":"A", "away_team":"B", "home_goals":1, "away_goals":0},
        {"kickoff":"2025-02-01", "home_team":"C", "away_team":"A", "home_goals":2, "away_goals":2},
    ]
    form = team_form(matches, "A", datetime(2025, 3, 1), None)
    assert form["sample"] == 2
    assert 1.8 < form["points_per_game"] < 2.0

def test_league_table_uses_current_season_before_fixture():
    matches = [
        {"competition":"League One", "season":"2024", "kickoff":"2024-01-01", "home_team":"A", "away_team":"B", "home_goals":0, "away_goals":5},
        {"competition":"League One", "season":"2025", "kickoff":"2025-01-01", "home_team":"A", "away_team":"B", "home_goals":2, "away_goals":0},
        {"competition":"League One", "season":"2025", "kickoff":"2025-01-02", "home_team":"C", "away_team":"A", "home_goals":1, "away_goals":1},
        {"competition":"League One", "season":"2025", "kickoff":"2025-02-01", "home_team":"B", "away_team":"A", "home_goals":9, "away_goals":0},
    ]
    table = league_table(matches, "League One", datetime(2025, 1, 15))
    assert table["A"]["position"] == 1
    assert table["A"]["points"] == 4
    assert table["B"]["position"] == 3
