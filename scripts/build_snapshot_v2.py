"""Build the no-cost static MatchSignal dashboard."""
import html
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from matchsignal.config import MODEL_VERSION
from matchsignal.database import connect

DATABASE = Path(os.environ.get("MATCHSIGNAL_DATABASE", ROOT / "data" / "matchsignal.sqlite"))
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

def match_time(value):
    kickoff = datetime.fromisoformat(str(value))
    hour = kickoff.hour % 12 or 12
    minute = f":{kickoff.minute:02d}" if kickoff.minute else ""
    suffix = "am" if kickoff.hour < 12 else "pm"
    return f"{kickoff.strftime('%A')} {hour}{minute}{suffix}"

def match_day(value):
    return datetime.fromisoformat(str(value)).strftime("%A")


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
    day_buttons = "".join(f"<button data-day={html.escape(day)}>{html.escape(day)}</button>" for day in DAYS)
    over_entries = "".join(
        f"<tr data-day={html.escape(match_day(row['kickoff']))}><td>{html.escape(match_time(row['kickoff']))}</td>"
        f"<td><b>{html.escape(row['home_team'])} vs {html.escape(row['away_team'])}</b>"
        f"<small>{html.escape(row['competition'])}</small></td>"
        f"<td>{html.escape(row['selection'])}</td>"
        f"<td class=prob>{row['predicted_probability']:.1%}</td></tr>"
        for row in (markets["over_2.5"] for _, markets in fixtures if markets.get("over_2.5"))
    ) or "<tr><td colspan=4>No fixtures in the next four days yet.</td></tr>"
    winner_fixtures = []
    for fixture, markets in by_fixture.items():
        if not all(market in markets for market in ("home_win", "draw", "away_win")):
            continue
        best_market = max(("home_win", "draw", "away_win"), key=lambda market: markets[market]["predicted_probability"])
        winner_fixtures.append((fixture, markets, best_market))
    winner_fixtures.sort(key=lambda item: (-item[1][item[2]]["predicted_probability"], item[0][0]))

    winner_rows = []
    for (kickoff, competition, home, away), markets, best_market in winner_fixtures:
        result_label = {"home_win": home, "draw": "Draw", "away_win": away}[best_market]
        winner_rows.append(
            f"<tr data-day={html.escape(match_day(kickoff))}><td>{html.escape(match_time(kickoff))}</td>"
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
.day-filter{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}}.day-filter button{{border:1px solid #294557;border-radius:8px;background:#0d2232;color:#eef5fa;padding:8px 11px;font-weight:700;cursor:pointer}}
.day-filter button.active{{background:#eef5fa;color:#08131f;border-color:#eef5fa}}tr.hidden,.empty-day.hidden{{display:none}}
.empty-day{{background:#102536;border-radius:10px;margin-top:18px;padding:16px;color:#a8bdca}}
@media(max-width:650px){{body{{padding:16px}}th:nth-child(1),td:nth-child(1){{display:none}}td{{padding:12px 10px}}}}
</style><header><h1>Match Signal</h1><p class=muted>English fixtures in the next four days | Model {MODEL_VERSION}</p></header>
<div class=tabs><button class=active data-tab=goals>Over 2.5 Goals</button><button data-tab=winners>Match Winners</button></div>
<div class=day-filter><button class=active data-day=all>All</button>{day_buttons}</div>
<section class="panel active" id=goals><h2>Fixtures ranked by goal probability</h2><p class="empty-day hidden">No fixtures for this day inside the four-day window.</p><table><thead><tr><th>Day / time</th><th>Fixture</th><th>Market</th><th>Probability</th></tr></thead><tbody>{over_entries}</tbody></table></section>
<section class=panel id=winners><h2>Fixtures ranked by likely result</h2><p class="empty-day hidden">No fixtures for this day inside the four-day window.</p><table><thead><tr><th>Day / time</th><th>Fixture</th><th>Likely result</th><th>Probability</th></tr></thead><tbody>{winner_entries}</tbody></table></section>
<footer class=muted><p>Probabilities are model estimates, not guarantees.</p></footer>"""
    page += """<script>
document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-tab]').forEach(item => item.classList.toggle('active', item === button));
  document.querySelectorAll('.panel').forEach(panel => panel.classList.toggle('active', panel.id === button.dataset.tab));
}));
document.querySelectorAll('[data-day]').forEach(button => button.addEventListener('click', () => {
  const day = button.dataset.day;
  document.querySelectorAll('.day-filter [data-day]').forEach(item => item.classList.toggle('active', item === button));
  document.querySelectorAll('tbody tr[data-day]').forEach(row => row.classList.toggle('hidden', day !== 'all' && row.dataset.day !== day));
  document.querySelectorAll('.panel').forEach(panel => {
    const rows = [...panel.querySelectorAll('tbody tr[data-day]')];
    const hasVisibleRows = rows.some(row => !row.classList.contains('hidden'));
    panel.querySelector('.empty-day').classList.toggle('hidden', hasVisibleRows);
    panel.querySelector('table').classList.toggle('hidden', !hasVisibleRows);
  });
}));
</script>"""
    (ROOT / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
