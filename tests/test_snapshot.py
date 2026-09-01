from datetime import date, timedelta

from matchsignal.database import connect
from scripts.build_snapshot_v2 import build_winner_entries, prediction_rows


def add_fixture_predictions(connection, kickoff, fixture_id):
    connection.execute(
        """INSERT INTO fixtures(
            external_fixture_id,competition,kickoff,home_team,away_team,status
        ) VALUES(?,?,?,?,?,?)""",
        (fixture_id, "Premier League", kickoff, f"Home {fixture_id}", f"Away {fixture_id}", "scheduled"),
    )
    database_id = connection.execute(
        "SELECT id FROM fixtures WHERE external_fixture_id=?", (fixture_id,)
    ).fetchone()["id"]
    for market, selection, probability in (
        ("home_win", "Home win", 0.55),
        ("draw", "Draw", 0.25),
        ("away_win", "Away win", 0.20),
        ("over_2.5", "Over 2.5 goals", 0.60),
    ):
        connection.execute(
            """INSERT INTO predictions(
                fixture_id,prediction_created_at,model_version,home_expected_goals,away_expected_goals,
                market,selection,predicted_probability,confidence
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (database_id, "2026-09-01", "test", 1.5, 1.0, market, selection, probability, "medium"),
        )
    connection.commit()


def test_prediction_rows_use_today_plus_the_next_four_calendar_days(tmp_path):
    connection = connect(tmp_path / "snapshot.sqlite")
    today = date(2026, 9, 1)
    for offset in (-1, 0, 1, 4, 5):
        kickoff = f"{today + timedelta(days=offset)}T15:00:00"
        add_fixture_predictions(connection, kickoff, str(offset))

    rows = prediction_rows(connection, today)
    fixture_dates = {row["kickoff"][:10] for row in rows}

    assert fixture_dates == {"2026-09-01", "2026-09-02", "2026-09-05"}


def test_match_winners_are_not_truncated_to_six():
    markets = {
        "home_win": {"predicted_probability": 0.55},
        "draw": {"predicted_probability": 0.25},
        "away_win": {"predicted_probability": 0.20},
    }
    fixtures = {
        (f"2026-09-0{day}T15:00:00", "Premier League", f"Home {day}", f"Away {day}"): markets
        for day in range(1, 8)
    }

    assert build_winner_entries(fixtures).count("<tr data-day=") == 7
