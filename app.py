import os
from pathlib import Path
from flask import Flask, abort, render_template_string, send_from_directory

from matchsignal.database import connect
from matchsignal.metrics import brier_score, calibration, log_loss
from matchsignal.scanner import strongest

app = Flask(__name__)
DATABASE_ENV = os.environ.get("MATCHSIGNAL_DATABASE")
DATABASE = Path(DATABASE_ENV) if DATABASE_ENV else None

def db(): return connect(DATABASE) if DATABASE and DATABASE.exists() else None

LAYOUT = """<!doctype html><title>Match Signal</title><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:auto;max-width:980px;padding:28px;background:#08131f;color:#eef5fa;font:16px Arial}a{color:#b8ff4e}nav{display:flex;gap:18px;margin:18px 0 30px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.card{background:#102536;padding:18px;border-radius:12px}small{color:#98aebb;text-transform:uppercase}b{display:block;font-size:1.3em;margin:7px 0}.muted{color:#98aebb}</style><h1>Match Signal</h1><p class=muted>English Football Probability Scanner · Model 2.0.0</p><nav><a href='/'>Signals</a><a href='/history'>History</a><a href='/performance'>Performance</a></nav>{{ body|safe }}"""


@app.get("/")
def home():
    connection = db()
    if not connection: return send_from_directory(".", "index.html")
    rows = connection.execute("""SELECT p.*,f.home_team,f.away_team,f.competition FROM predictions p JOIN fixtures f ON f.id=p.fixture_id WHERE p.settled_at IS NULL""").fetchall()
    signals = strongest([{"probability": row["predicted_probability"], "fixture": f"{row['home_team']} vs {row['away_team']}", "selection": row["selection"], "confidence": row["confidence"], "competition": row["competition"]} for row in rows])[:20]
    body = "<h2>Today's strongest signals</h2><div class=grid>" + "".join(f"<article class=card><small>{s['competition']} · {s['confidence']}</small><b>{s['fixture']}</b><p>{s['selection']} · <strong>{s['probability']:.1%}</strong></p></article>" for s in signals) + "</div>" if signals else "<h2>No eligible signals yet</h2><p class=muted>Run the refresh pipeline once historical data and upcoming fixtures are available.</p>"
    return render_template_string(LAYOUT, body=body)


@app.get("/mockup")
def mockup():
    """Visual preview of the expanded, team-specific fixture card."""
    return render_template_string("""<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>
    <title>Match Signal card preview</title><style>
    body{margin:0;background:#07111d;color:#ecf4fa;font:15px system-ui,Arial;padding:22px}.card{max-width:620px;margin:auto;background:#102536;border:1px solid #214154;border-radius:18px;overflow:hidden;box-shadow:0 14px 40px #0006}.head{padding:22px;background:linear-gradient(135deg,#15354a,#102536)}.eyebrow{color:#b8ff4e;text-transform:uppercase;letter-spacing:.11em;font-size:11px;font-weight:700}.teams{display:flex;justify-content:space-between;align-items:center;font-size:23px;font-weight:800;margin:12px 0 5px}.muted{color:#9bb1c0}.score{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:16px}.metric,.market{background:#0b1c2a;border-radius:11px;padding:11px}.metric b,.market b{display:block;font-size:19px;margin-top:3px}.label{color:#9bb1c0;font-size:11px;text-transform:uppercase;letter-spacing:.06em}.tabs{display:flex;gap:8px;padding:0 16px 16px;overflow:auto}.tab{white-space:nowrap;border:1px solid #2a4e62;border-radius:99px;padding:7px 10px;color:#b9ceda}.tab.active{background:#b8ff4e;color:#0c1b27;border-color:#b8ff4e;font-weight:700}.section{padding:16px;border-top:1px solid #214154}.section h2{font-size:14px;margin:0 0 11px}.split{display:grid;grid-template-columns:1fr 1fr;gap:8px}.market b{color:#b8ff4e}.note{padding:0 16px 18px;color:#9bb1c0;font-size:12px}</style>
    <main class=card><header class=head><div class=eyebrow>Championship · Fri 14 Aug · 19:00</div><div class=teams><span>Wolves</span><span class=muted>vs</span><span>Blackburn</span></div><div class=muted>Model 2.1.0 · Team-stat preview</div></header>
    <section class=score><div class=metric><span class=label>Wolves win</span><b>47.9%</b></div><div class=metric><span class=label>Draw</span><b>26.2%</b></div><div class=metric><span class=label>Blackburn win</span><b>25.9%</b></div></section>
    <nav class=tabs><span class="tab active">Overview</span><span class=tab>Goals</span><span class=tab>Shots</span><span class=tab>Corners</span><span class=tab>Discipline</span></nav>
    <section class=section><h2>Team shots</h2><div class=split><div class=market><span class=label>Wolves 10+ shots</span><b>85.8%</b></div><div class=market><span class=label>Blackburn 9+ shots</span><b>85.6%</b></div><div class=market><span class=label>Wolves 3+ on target</span><b>80.8%</b></div><div class=market><span class=label>Blackburn 3+ on target</span><b>73.8%</b></div></div></section>
    <section class=section><h2>Team corners</h2><div class=split><div class=market><span class=label>Wolves 4+ corners</span><b>71.9%</b></div><div class=market><span class=label>Blackburn 4+ corners</span><b>72.2%</b></div></div></section>
    <section class=section><h2>Discipline</h2><div class=split><div class=market><span class=label>Wolves 9+ fouls</span><b>80.0%</b></div><div class=market><span class=label>Blackburn 9+ fouls</span><b>75.5%</b></div><div class=market><span class=label>Wolves 2+ cards</span><b>51.5%</b></div><div class=market><span class=label>Blackburn 2+ cards</span><b>59.8%</b></div></div></section>
    <p class=note>Preview figures use historical team-level data. Markets remain hidden when the supporting data is insufficient.</p></main>""")

@app.get('/history')
def history():
    connection = db()
    rows = connection.execute("""SELECT f.kickoff,f.home_team,f.away_team,p.selection,p.predicted_probability,p.correct FROM predictions p JOIN fixtures f ON f.id=p.fixture_id WHERE p.settled_at IS NOT NULL ORDER BY f.kickoff DESC LIMIT 200""").fetchall() if connection else []
    body = "<h2>Prediction history</h2>" + "".join(f"<p>{r['kickoff']} · {r['home_team']} vs {r['away_team']} · {r['selection']} {r['predicted_probability']:.1%} · {'Correct' if r['correct'] else 'Incorrect'}</p>" for r in rows)
    return render_template_string(LAYOUT, body=body or '<p class=muted>No settled predictions yet.</p>')

@app.get('/performance')
def performance():
    connection = db(); rows = connection.execute("SELECT predicted_probability,actual_outcome FROM predictions WHERE settled_at IS NOT NULL").fetchall() if connection else []
    pairs = [(row["predicted_probability"], row["actual_outcome"]) for row in rows]
    body = f"<h2>Performance</h2><p>Total predictions: {len(pairs)}</p><p>Brier score: {brier_score(pairs)}</p><p>Log loss: {log_loss(pairs)}</p>" + "".join(f"<p>{bucket['bucket']}: predicted {bucket['predicted']:.1%}, occurred {bucket['actual']:.1%} ({bucket['count']})</p>" for bucket in calibration(pairs))
    return render_template_string(LAYOUT, body=body)

@app.get('/fixtures/<int:fixture_id>')
def fixture_detail(fixture_id):
    connection = db()
    if not connection: abort(404)
    fixture = connection.execute("SELECT * FROM fixtures WHERE id=?", (fixture_id,)).fetchone()
    if not fixture: abort(404)
    predictions = connection.execute("SELECT selection,predicted_probability,confidence,home_expected_goals,away_expected_goals FROM predictions WHERE fixture_id=? ORDER BY predicted_probability DESC", (fixture_id,)).fetchall()
    body = f"<h2>{fixture['home_team']} vs {fixture['away_team']}</h2><p>{fixture['competition']} · {fixture['kickoff']}</p>"
    if predictions:
        body += f"<p>Expected goals: {predictions[0]['home_expected_goals']:.2f} – {predictions[0]['away_expected_goals']:.2f}</p>" + "".join(f"<p>{p['selection']}: <b>{p['predicted_probability']:.1%}</b> · {p['confidence']}</p>" for p in predictions)
    return render_template_string(LAYOUT, body=body)


@app.get("/health")
def health():
    return {"status": "ok"}
