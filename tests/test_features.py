from datetime import datetime
from matchsignal.features import team_form

def test_form_does_not_use_future_matches():
    matches = [
        {"kickoff":"2025-01-01", "home_team":"A", "away_team":"B", "home_goals":1, "away_goals":0},
        {"kickoff":"2025-02-01", "home_team":"A", "away_team":"B", "home_goals":9, "away_goals":0},
    ]
    form = team_form(matches, "A", datetime(2025, 1, 15), True)
    assert form["sample"] == 1
    assert form["goals_for"] == 1
