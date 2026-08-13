import os
from pathlib import Path
from flask import Flask, abort, render_template_string, send_from_directory

from matchsignal.database import connect
from matchsignal.metrics import brier_score, calibration, log_loss
from matchsignal.scanner import strongest

app = Flask(__name__)
DATABASE = Path(os.environ.get("MATCHSIGNAL_DATABASE", "data/matchsignal.sqlite"))

def db(): return connect(DATABASE) if DATABASE.exists() else None

LAYOUT = """<!doctype html><title>Match Signal</title><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:auto;max-width:980px;padding:28px;background:#08131f;color:#eef5fa;font:16px Arial}a{color:#b8ff4e}nav{display:flex;gap:18px;margin:18px 0 30px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.card{background:#102536;padding:18px;border-radius:12px}small{color:#98aebb;text-transform:uppercase}b{display:block;font-size:1.3em;margin:7px 0}.muted{color:#98aebb}</style><h1>Match Signal</h1><p class=muted>English Football Probability Scanner · Model 2.0.0</p><nav><a href='/'>Signals</a><a href='/history'>History</a><a href='/performance'>Performance</a></nav>{{ body|safe }}"""


@app.get("/")
def home():
    connection = db()
    if not connection: return send_from_directory(".", "index.html")
    rows = connection.execute("""SELECT p.*,f.home_team,f.away_team,f.competition FROM predictions p JOIN fixtures f ON f.id=p.fixture_id WHERE p.settled_at IS NULL""").fetchall()
    signals = strongest([{"probability": row["predicted_probability"], "fixture": f"{row['home_team']} vs {row['away_team']}", "selection": row["selection"], "confidence": row["confidence"], "competition": row["competition"]} for row in rows])[:20]
    body = "<h2>Today's strongest signals</h2><div class=grid>" + "".join(f"<article class=card><small>{s['competition']} · {s['confidence']}</small><b>{s['fixture']}</b><p>{s['selection']} · <strong>{s['probability']:.1%}</strong></p></article>" for s in signals) + "</div>" if signals else "<h2>No eligible signals yet</h2><p class=muted>Run the refresh pipeline once historical data and upcoming fixtures are available.</p>"
    return render_template_string(LAYOUT, body=body)

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
