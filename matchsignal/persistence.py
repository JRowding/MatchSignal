from datetime import datetime, timezone

from .config import CONFIG, MODEL_VERSION
from .scanner import LABELS

WINNER_MARKETS = {"home_win", "draw", "away_win"}
BTTS_WINNER_MARKETS = {"home_win_btts", "away_win_btts"}


def market_group(market: str) -> str:
    if market in WINNER_MARKETS:
        return "Match Winner"
    if market.startswith("over_"):
        return "Goals"
    if market.startswith("btts_"):
        return "BTTS"
    if market in BTTS_WINNER_MARKETS:
        return "BTTS + Winner"
    if "_shots_on_target_" in market:
        return "Team shots on target"
    if "_shots_" in market or market.startswith("shots_"):
        return "Team shots"
    if "fouls" in market:
        return "Team fouls"
    if "cards" in market:
        return "Team cards"
    if "corners" in market:
        return "Team corners"
    return "Other"


def probability_bucket(probability: float) -> str:
    start = min(90, int(probability * 10) * 10)
    return f"{start}-{start + 9}%"


def market_outcome(market: str, home: int, away: int) -> bool | None:
    total = home + away
    return {
        "home_win": home > away,
        "draw": home == away,
        "away_win": away > home,
        "over_0.5": total > .5,
        "over_1.5": total > 1.5,
        "over_2.5": total > 2.5,
        "over_3.5": total > 3.5,
        "btts_yes": home > 0 and away > 0,
        "btts_no": home == 0 or away == 0,
        "home_win_btts": home > away and home > 0 and away > 0,
        "away_win_btts": away > home and home > 0 and away > 0,
        "home_over_0.5": home > .5,
        "home_over_1.5": home > 1.5,
        "away_over_0.5": away > .5,
        "away_over_1.5": away > 1.5,
    }.get(market)


def persist_prediction(connection, fixture, forecast):
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inserted = 0
    for market, probability in forecast["probabilities"].items():
        if market not in CONFIG.enabled_markets or market not in LABELS: continue
        cursor = connection.execute("""INSERT OR IGNORE INTO predictions(
            fixture_id,prediction_created_at,model_version,home_expected_goals,away_expected_goals,
            market,selection,predicted_probability,confidence,frozen_at,fixture_kickoff,
            competition,home_team,away_team,market_group,probability_bucket
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            fixture["id"], created, MODEL_VERSION, forecast["home_xg"], forecast["away_xg"],
            market, LABELS[market], probability, forecast["confidence"], created,
            fixture["kickoff"], fixture["competition"], fixture["home_team"], fixture["away_team"],
            market_group(market), probability_bucket(probability),
        ))
        inserted += cursor.rowcount
    connection.commit()
    return inserted

def settle_predictions(connection):
    rows = connection.execute("""SELECT p.id,p.market,m.home_goals,m.away_goals FROM predictions p JOIN fixtures f ON p.fixture_id=f.id JOIN matches_v2 m ON m.competition=f.competition AND m.kickoff=f.kickoff AND m.home_team=f.home_team AND m.away_team=f.away_team WHERE p.settled_at IS NULL AND m.completed=1""").fetchall()
    settled = 0
    for row in rows:
        home, away = row["home_goals"], row["away_goals"]
        outcome = market_outcome(row["market"], home, away)
        if outcome is not None:
            connection.execute(
                """UPDATE predictions
                SET actual_outcome=?,correct=?,settled_at=?,actual_home_goals=?,actual_away_goals=?
                WHERE id=?""",
                (
                    int(outcome), int(outcome), datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    home, away, row["id"],
                ),
            )
            settled += 1
    connection.commit(); return settled
