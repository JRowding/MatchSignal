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

LAYOUT = """<!doctype html><title>Match Signal</title><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:auto;max-width:1080px;padding:28px;background:#08131f;color:#eef5fa;font:16px Arial}a{color:#b8ff4e}nav{display:flex;gap:18px;margin:18px 0 30px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.card{background:#102536;padding:18px;border-radius:8px}small{color:#98aebb;text-transform:uppercase}b{display:block;font-size:1.3em;margin:7px 0}.muted{color:#98aebb}table{width:100%;border-collapse:collapse;margin:12px 0 28px}th,td{border-bottom:1px solid #214154;padding:10px;text-align:left}th{color:#98aebb;font-size:12px;text-transform:uppercase}.pill{display:inline-block;background:#17364c;border-radius:999px;padding:4px 8px}</style><h1>Match Signal</h1><p class=muted>English Football Probability Scanner · Model 2.5.0</p><nav><a href='/'>Signals</a><a href='/history'>History</a><a href='/performance'>Performance</a></nav>{{ body|safe }}"""


def pct(value):
    return f"{value:.1%}" if value is not None else "-"


def score(value):
    return f"{value:.3f}" if value is not None else "-"


def performance_table(title, rows, label):
    if not rows:
        return f"<h3>{title}</h3><p class=muted>No settled predictions yet.</p>"
    body = "".join(
        f"<tr><td>{row[label] or 'Unknown'}</td><td>{row['total']}</td><td>{pct(row['accuracy'])}</td><td>{pct(row['avg_probability'])}</td><td>{score(row['brier'])}</td></tr>"
        for row in rows
    )
    return f"<h3>{title}</h3><table><tr><th>{label.replace('_', ' ')}</th><th>Predictions</th><th>Accuracy</th><th>Avg probability</th><th>Brier</th></tr>{body}</table>"


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
    rows = connection.execute("""SELECT COALESCE(p.fixture_kickoff,f.kickoff) AS kickoff,COALESCE(p.home_team,f.home_team) AS home_team,COALESCE(p.away_team,f.away_team) AS away_team,p.selection,p.predicted_probability,p.correct,p.actual_home_goals,p.actual_away_goals,p.market_group FROM predictions p JOIN fixtures f ON f.id=p.fixture_id WHERE p.settled_at IS NOT NULL ORDER BY kickoff DESC LIMIT 200""").fetchall() if connection else []
    if not rows:
        return render_template_string(LAYOUT, body="<h2>Prediction history</h2><p class=muted>No settled predictions yet.</p>")
    body = "<h2>Prediction history</h2>" + "".join(f"<p>{r['kickoff']} · {r['home_team']} {r['actual_home_goals'] if r['actual_home_goals'] is not None else ''} - {r['actual_away_goals'] if r['actual_away_goals'] is not None else ''} {r['away_team']} · <span class=pill>{r['market_group'] or 'Market'}</span> {r['selection']} {r['predicted_probability']:.1%} · {'Correct' if r['correct'] else 'Incorrect'}</p>" for r in rows)
    return render_template_string(LAYOUT, body=body)

@app.get('/performance')
def performance():
    connection = db(); rows = connection.execute("SELECT predicted_probability,actual_outcome FROM predictions WHERE settled_at IS NOT NULL").fetchall() if connection else []
    pairs = [(row["predicted_probability"], row["actual_outcome"]) for row in rows]
    if not connection:
        return render_template_string(LAYOUT, body="<h2>Performance</h2><p class=muted>No database configured yet.</p>")
    by_league = connection.execute("""SELECT COALESCE(competition,'Unknown') AS competition,COUNT(*) AS total,AVG(correct) AS accuracy,AVG(predicted_probability) AS avg_probability,AVG((predicted_probability - actual_outcome) * (predicted_probability - actual_outcome)) AS brier FROM predictions WHERE settled_at IS NOT NULL GROUP BY 1 ORDER BY total DESC""").fetchall()
    by_market = connection.execute("""SELECT COALESCE(market_group,market) AS market_group,COUNT(*) AS total,AVG(correct) AS accuracy,AVG(predicted_probability) AS avg_probability,AVG((predicted_probability - actual_outcome) * (predicted_probability - actual_outcome)) AS brier FROM predictions WHERE settled_at IS NOT NULL GROUP BY 1 ORDER BY total DESC""").fetchall()
    by_probability = connection.execute("""SELECT COALESCE(probability_bucket,'Unknown') AS probability_bucket,COUNT(*) AS total,AVG(correct) AS accuracy,AVG(predicted_probability) AS avg_probability,AVG((predicted_probability - actual_outcome) * (predicted_probability - actual_outcome)) AS brier FROM predictions WHERE settled_at IS NOT NULL GROUP BY 1 ORDER BY probability_bucket""").fetchall()
    body = (
        f"<h2>Prediction Tracker</h2><div class=grid><article class=card><small>Settled predictions</small><b>{len(pairs)}</b></article>"
        f"<article class=card><small>Overall accuracy</small><b>{pct(sum(outcome for _, outcome in pairs) / len(pairs)) if pairs else '-'}</b></article>"
        f"<article class=card><small>Brier score</small><b>{score(brier_score(pairs))}</b></article><article class=card><small>Log loss</small><b>{score(log_loss(pairs))}</b></article></div>"
        "<h3>Calibration</h3>"
        + "".join(f"<p>{bucket['bucket']}: predicted {bucket['predicted']:.1%}, occurred {bucket['actual']:.1%} ({bucket['count']})</p>" for bucket in calibration(pairs))
        + performance_table("By League", by_league, "competition")
        + performance_table("By Market", by_market, "market_group")
        + performance_table("By Probability Range", by_probability, "probability_bucket")
    )
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
