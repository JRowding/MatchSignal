"""Generate the free-hosting static dashboard from persisted predictions."""
import html
import os
from pathlib import Path

from matchsignal.database import connect
from matchsignal.scanner import strongest

ROOT = Path(__file__).resolve().parents[1]
DATABASE = Path(os.environ.get("MATCHSIGNAL_DATABASE", ROOT / "data" / "matchsignal.sqlite"))

def main():
    connection = connect(DATABASE)
    rows = connection.execute("""SELECT p.predicted_probability,p.selection,p.confidence,f.home_team,f.away_team,f.competition,f.kickoff FROM predictions p JOIN fixtures f ON f.id=p.fixture_id WHERE p.settled_at IS NULL""").fetchall()
    signals = strongest([dict(row) | {"probability": row["predicted_probability"]} for row in rows])[:24]
    cards = "".join(f"<article><small>{html.escape(s['competition'])} · {html.escape(s['confidence'])}</small><h2>{html.escape(s['home_team'])} vs {html.escape(s['away_team'])}</h2><p>{html.escape(s['selection'])}</p><b>{s['probability']:.1%}</b></article>" for s in signals)
    if not cards: cards = "<p>No eligible signals are available yet. The next successful fixture update will populate this page.</p>"
    (ROOT / "index.html").write_text(f"""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Match Signal</title><style>body{{margin:auto;max-width:1100px;padding:32px;background:#08131f;color:#eef5fa;font:16px Arial}}header{{border-bottom:1px solid #294557;padding-bottom:20px}}h1{{font-size:3rem;margin:0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-top:24px}}article{{background:#102536;border:1px solid #294557;border-radius:14px;padding:18px}}small{{color:#a8bdca;text-transform:uppercase}}h2{{font-size:1.2rem}}b{{font-size:2rem;color:#b8ff4e}}</style><header><h1>Match Signal</h1><p>Today's English Football Probability Scanner · Model 2.0.0</p></header><h3>Strongest signals</h3><main class=grid>{cards}</main><footer><p>Probabilities are model estimates, not guarantees.</p></footer>""", encoding="utf-8")

if __name__ == "__main__": main()
