from datetime import datetime, timezone

from .config import CONFIG, MODEL_VERSION
from .scanner import LABELS

def persist_prediction(connection, fixture, forecast):
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for market, probability in forecast["probabilities"].items():
        if market not in CONFIG.enabled_markets or market not in LABELS: continue
        connection.execute("""INSERT OR IGNORE INTO predictions(fixture_id,prediction_created_at,model_version,home_expected_goals,away_expected_goals,market,selection,predicted_probability,confidence)
        VALUES(?,?,?,?,?,?,?,?,?)""", (fixture["id"], created, MODEL_VERSION, forecast["home_xg"], forecast["away_xg"], market, LABELS[market], probability, forecast["confidence"]))
    connection.commit()

def settle_predictions(connection):
    rows = connection.execute("""SELECT p.id,p.market,m.home_goals,m.away_goals FROM predictions p JOIN fixtures f ON p.fixture_id=f.id JOIN matches_v2 m ON m.competition=f.competition AND m.kickoff=f.kickoff AND m.home_team=f.home_team AND m.away_team=f.away_team WHERE p.settled_at IS NULL AND m.completed=1""").fetchall()
    for row in rows:
        home, away = row["home_goals"], row["away_goals"]; total = home + away
        outcome = {"home_win": home > away, "draw": home == away, "away_win": away > home,
                   "over_0.5": total > .5, "over_1.5": total > 1.5, "over_2.5": total > 2.5, "over_3.5": total > 3.5,
                   "btts_yes": home > 0 and away > 0, "btts_no": home == 0 or away == 0,
                   "home_win_btts": home > away and home > 0 and away > 0,
                   "away_win_btts": away > home and home > 0 and away > 0,
                   "home_over_0.5": home > .5, "home_over_1.5": home > 1.5, "away_over_0.5": away > .5, "away_over_1.5": away > 1.5}.get(row["market"])
        if outcome is not None: connection.execute("UPDATE predictions SET actual_outcome=?,correct=?,settled_at=? WHERE id=?", (int(outcome), int(outcome), datetime.now(timezone.utc).isoformat(timespec="seconds"), row["id"]))
    connection.commit(); return len(rows)
