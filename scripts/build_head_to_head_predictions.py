import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB = Path(__file__).parent / "football_data.sqlite"


def norm(value):
    import re, unicodedata
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"\b(fc|cf|ac|afc|fk|sc|the)\b", " ", value)
    return re.sub(r"[^a-z0-9]", "", value)


def main():
    con = sqlite3.connect(DB)
    con.executescript("""
      CREATE TABLE IF NOT EXISTS head_to_head_predictions (
        fixture_id INTEGER PRIMARY KEY,
        seasons_used TEXT NOT NULL,
        matches_used INTEGER NOT NULL,
        home_wins INTEGER NOT NULL,
        draws INTEGER NOT NULL,
        away_wins INTEGER NOT NULL,
        predicted_outcome TEXT,
        confidence TEXT NOT NULL,
        FOREIGN KEY(fixture_id) REFERENCES live_fixtures(id)
      );
      DELETE FROM head_to_head_predictions;
    """)
    existing = {row[1] for row in con.execute("PRAGMA table_info(head_to_head_predictions)")}
    for name in ("predicted_team TEXT", "team_win_likelihood REAL", "home_result_likelihood REAL", "draw_result_likelihood REAL", "away_result_likelihood REAL", "over_0_5_likelihood REAL", "over_1_5_likelihood REAL", "over_2_5_likelihood REAL", "fixtures_used TEXT"):
        column = name.split()[0]
        if column not in existing:
            con.execute(f"ALTER TABLE head_to_head_predictions ADD COLUMN {name}")
    fixtures = con.execute("""
      SELECT l.id, l.country, l.competition, l.home_team, l.away_team
      FROM live_fixtures l JOIN prediction_candidates p ON p.fixture_id = l.id
    """).fetchall()
    matchup = {}
    for country, season, date, home, away, outcome, home_goals, away_goals in con.execute("SELECT country, season, match_date, home_team, away_team, full_time_result, full_time_home_goals, full_time_away_goals FROM matches"):
        digits = "".join(ch for ch in season if ch.isdigit())
        canonical_season = f"20{digits[:2]}/20{digits[2:4]}" if len(digits) == 4 and len(season) == 4 and not digits.startswith("20") else season
        if canonical_season != "current" and int("".join(ch for ch in canonical_season if ch.isdigit())[:4] or 0) < 2023:
            continue
        matchup.setdefault((norm(country), norm(home), norm(away)), []).append((canonical_season, date or "", outcome, home_goals, away_goals))

    def season_rank(season):
        if season == "current":
            return 9999
        digits = "".join(ch for ch in season if ch.isdigit())
        return int(digits[:4] or 0)

    for fixture_id, country, competition, home, away in fixtures:
        # Limit the comparison to the newest three seasons available for this
        # exact home-away pairing. Reverse fixtures never enter this query.
        history = matchup.get((norm(country), norm(home), norm(away)), [])
        available = sorted({season for season, *_ in history}, key=season_rank, reverse=True)
        if not available:
            con.execute("INSERT INTO head_to_head_predictions(fixture_id,seasons_used,matches_used,home_wins,draws,away_wins,predicted_outcome,confidence) VALUES(?,?,?,?,?,?,?,?)", (fixture_id, "", 0, 0, 0, 0, None, "no direct history"))
            continue
        newest = season_rank(available[0])
        seasons = [season for season in available if season_rank(season) >= newest - 2]
        entries = {(season, date, outcome, home_goals, away_goals) for season, date, outcome, home_goals, away_goals in history if season in seasons and outcome}
        def date_rank(entry):
            try:
                return datetime.strptime(entry[1], "%d/%m/%Y")
            except ValueError:
                return datetime.min
        entries = sorted(entries, key=date_rank, reverse=True)[:5]
        if len(entries) < 3:
            con.execute("INSERT INTO head_to_head_predictions(fixture_id,seasons_used,matches_used,home_wins,draws,away_wins,predicted_outcome,confidence) VALUES(?,?,?,?,?,?,?,?)", (fixture_id, ", ".join(seasons), len(entries), 0, 0, 0, None, "fewer than three recent direct fixtures"))
            continue
        counts = {}; weighted = {"H": 0.0, "D": 0.0, "A": 0.0}; total_goals = []
        weights = (1.0, 0.85, 0.7, 0.55, 0.4)
        for index, (_, _, outcome, home_goals, away_goals) in enumerate(entries):
            counts[outcome] = counts.get(outcome, 0) + 1
            weighted[outcome] += weights[index]
            if home_goals is not None and away_goals is not None:
                total_goals.append((home_goals + away_goals, weights[index]))
        wins, draws, losses = counts.get("H", 0), counts.get("D", 0), counts.get("A", 0)
        total = wins + draws + losses
        best = max((weighted["H"], "home win"), (weighted["D"], "draw"), (weighted["A"], "away win")) if total else (0, None)
        tied = sum(value == best[0] for value in weighted.values()) > 1
        prediction = None if tied or not best[0] else best[1]
        confidence = "high" if total >= 5 and not tied else "medium" if not tied else "limited"
        total_weight = sum(weighted.values())
        team = home if weighted["H"] > weighted["A"] else away if weighted["A"] > weighted["H"] else None
        team_likelihood = (max(weighted["H"], weighted["A"]) / total_weight * 100) if team and total_weight else None
        def likelihood(threshold):
            return (sum(weight for goals, weight in total_goals if goals > threshold) / sum(weight for _, weight in total_goals) * 100) if total_goals else None
        con.execute("""INSERT INTO head_to_head_predictions(
          fixture_id,seasons_used,matches_used,home_wins,draws,away_wins,predicted_outcome,confidence,
          predicted_team,team_win_likelihood,home_result_likelihood,draw_result_likelihood,away_result_likelihood,over_0_5_likelihood,over_1_5_likelihood,over_2_5_likelihood,fixtures_used
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (fixture_id, ", ".join(seasons), total, wins, draws, losses, prediction, confidence, team, team_likelihood, weighted["H"] / total_weight * 100, weighted["D"] / total_weight * 100, weighted["A"] / total_weight * 100, likelihood(0.5), likelihood(1.5), likelihood(2.5), json.dumps(entries, default=str)))
    con.commit()
    print("fixtures", con.execute("SELECT COUNT(*) FROM head_to_head_predictions").fetchone()[0])
    print("outcomes", con.execute("SELECT COUNT(*) FROM head_to_head_predictions WHERE predicted_outcome IS NOT NULL").fetchone()[0])
    con.close()


if __name__ == "__main__":
    main()
