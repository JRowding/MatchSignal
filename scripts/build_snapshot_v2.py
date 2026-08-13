"""Build the no-cost static Over 2.5 Goals dashboard."""
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
    rows = connection.execute("""SELECT p.predicted_probability,p.selection,p.confidence,
        f.home_team,f.away_team,f.competition,f.kickoff
        FROM predictions p JOIN fixtures f ON f.id=p.fixture_id
        WHERE p.settled_at IS NULL AND p.market='over_2.5'
        ORDER BY p.predicted_probability DESC, f.kickoff""").fetchall()
    entries = "".join(
        f"<tr><td>{html.escape(str(row['kickoff'])[:16].replace('T', ' '))}</td>"
        f"<td><b>{html.escape(row['home_team'])} vs {html.escape(row['away_team'])}</b>"
        f"<small>{html.escape(row['competition'])}</small></td>"
        f"<td>{html.escape(row['selection'])}</td>"
        f"<td class=prob>{row['predicted_probability']:.1%}</td>"
        f"<td>{html.escape(row['confidence'])}</td></tr>"
        for row in rows
    ) or "<tr><td colspan=5>No fixtures in the next four days yet.</td></tr>"
    page = f"""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Match Signal</title><style>
body{{margin:auto;max-width:1100px;padding:24px;background:#08131f;color:#eef5fa;font:16px Arial}}
header{{border-bottom:1px solid #294557;padding-bottom:18px}}h1{{font-size:2.4rem;margin:0}}
.muted,small{{color:#a8bdca}}table{{width:100%;border-collapse:separate;border-spacing:0 8px;margin-top:18px}}
th{{text-align:left;color:#a8bdca;font-size:11px;text-transform:uppercase;padding:0 12px 5px}}
td{{background:#102536;padding:13px 12px}}td:first-child{{border-radius:10px 0 0 10px;white-space:nowrap}}
td:last-child{{border-radius:0 10px 10px 0}}td b,td small{{display:block}}.prob{{color:#b8ff4e;font-size:1.25rem;font-weight:bold}}
@media(max-width:650px){{body{{padding:16px}}th:nth-child(1),td:nth-child(1),th:nth-child(5),td:nth-child(5){{display:none}}}}
</style><header><h1>Match Signal</h1><p class=muted>Over 2.5 Goals | English fixtures in the next four days | Model {MODEL_VERSION}</p></header>
<h2>Fixtures ranked by probability</h2><table><thead><tr><th>Kickoff</th><th>Fixture</th><th>Market</th><th>Probability</th><th>Confidence</th></tr></thead><tbody>{entries}</tbody></table>
<footer class=muted><p>Probabilities are model estimates, not guarantees.</p></footer>"""
    (ROOT / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
