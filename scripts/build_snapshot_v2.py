"""Build the no-cost static MatchSignal dashboard."""
import html
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from matchsignal.config import MODEL_VERSION
from matchsignal.database import connect

DATABASE = Path(os.environ.get("MATCHSIGNAL_DATABASE", ROOT / "data" / "matchsignal.sqlite"))


def main():
    connection = connect(DATABASE)
    rows = connection.execute("""SELECT p.market,p.predicted_probability,p.selection,
        f.home_team,f.away_team,f.competition,f.kickoff
        FROM predictions p JOIN fixtures f ON f.id=p.fixture_id
        WHERE p.settled_at IS NULL AND p.market IN ('home_win','draw','away_win','over_2.5')
        ORDER BY f.kickoff, f.competition, f.home_team, p.market""").fetchall()
    by_fixture = {}
    for row in rows:
        key = (row["kickoff"], row["competition"], row["home_team"], row["away_team"])
        by_fixture.setdefault(key, {})[row["market"]] = row
    fixtures = sorted(by_fixture.items(), key=lambda item: (
        -(item[1].get("over_2.5")["predicted_probability"] if item[1].get("over_2.5") else 0),
        item[0][0],
    ))
    over_entries = "".join(
        f"<tr><td>{html.escape(str(row['kickoff'])[:16].replace('T', ' '))}</td>"
        f"<td><b>{html.escape(row['home_team'])} vs {html.escape(row['away_team'])}</b>"
        f"<small>{html.escape(row['competition'])}</small></td>"
        f"<td>{html.escape(row['selection'])}</td>"
        f"<td class=prob>{row['predicted_probability']:.1%}</td></tr>"
        for row in (markets["over_2.5"] for _, markets in fixtures if markets.get("over_2.5"))
    ) or "<tr><td colspan=4>No fixtures in the next four days yet.</td></tr>"
    winner_rows = []
    for (kickoff, competition, home, away), markets in fixtures:
        if not all(market in markets for market in ("home_win", "draw", "away_win")):
            continue
        best_market = max(("home_win", "draw", "away_win"), key=lambda market: markets[market]["predicted_probability"])
        result_label = {"home_win": home, "draw": "Draw", "away_win": away}[best_market]
        winner_rows.append(
            f"<tr><td>{html.escape(str(kickoff)[:16].replace('T', ' '))}</td>"
            f"<td><b>{html.escape(home)} vs {html.escape(away)}</b><small>{html.escape(competition)}</small></td>"
            f"<td><b>{html.escape(result_label)}</b><small>H {markets['home_win']['predicted_probability']:.1%} | "
            f"D {markets['draw']['predicted_probability']:.1%} | A {markets['away_win']['predicted_probability']:.1%}</small></td>"
            f"<td class=prob>{markets[best_market]['predicted_probability']:.1%}</td></tr>"
        )
    winner_entries = "".join(winner_rows) or "<tr><td colspan=4>No match-winner predictions in the next four days yet.</td></tr>"
    page = f"""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Match Signal</title><style>
body{{margin:auto;max-width:1100px;padding:24px;background:#08131f;color:#eef5fa;font:16px Arial}}
header{{border-bottom:1px solid #294557;padding-bottom:18px}}h1{{font-size:2.4rem;margin:0}}
.muted,small{{color:#a8bdca}}table{{width:100%;border-collapse:separate;border-spacing:0 8px;margin-top:18px}}
th{{text-align:left;color:#a8bdca;font-size:11px;text-transform:uppercase;padding:0 12px 5px}}
td{{background:#102536;padding:13px 12px}}td:first-child{{border-radius:10px 0 0 10px;white-space:nowrap}}
td:last-child{{border-radius:0 10px 10px 0}}td b,td small{{display:block}}.prob{{color:#b8ff4e;font-size:1.25rem;font-weight:bold}}
.tabs{{display:flex;gap:8px;margin-top:18px}}.tabs button{{border:1px solid #294557;border-radius:999px;background:#102536;color:#eef5fa;padding:9px 14px;font-weight:700;cursor:pointer}}
.tabs button.active{{background:#b8ff4e;color:#08131f;border-color:#b8ff4e}}.panel{{display:none}}.panel.active{{display:block}}
@media(max-width:650px){{body{{padding:16px}}th:nth-child(1),td:nth-child(1){{display:none}}td{{padding:12px 10px}}}}
</style><header><h1>Match Signal</h1><p class=muted>English fixtures in the next four days | Model {MODEL_VERSION}</p></header>
<div class=tabs><button class=active data-tab=goals>Over 2.5 Goals</button><button data-tab=winners>Match Winners</button></div>
<section class="panel active" id=goals><h2>Fixtures ranked by goal probability</h2><table><thead><tr><th>Kickoff</th><th>Fixture</th><th>Market</th><th>Probability</th></tr></thead><tbody>{over_entries}</tbody></table></section>
<section class=panel id=winners><h2>Fixtures ranked by likely result</h2><table><thead><tr><th>Kickoff</th><th>Fixture</th><th>Likely result</th><th>Probability</th></tr></thead><tbody>{winner_entries}</tbody></table></section>
<footer class=muted><p>Probabilities are model estimates, not guarantees.</p></footer>"""
    page += """<script>
document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-tab]').forEach(item => item.classList.toggle('active', item === button));
  document.querySelectorAll('.panel').forEach(panel => panel.classList.toggle('active', panel.id === button.dataset.tab));
}));
</script>"""
    (ROOT / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
