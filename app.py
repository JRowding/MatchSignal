import os
from pathlib import Path
from flask import Flask, abort, render_template_string, send_from_directory, g, request
from matchsignal.reporting import tracker_body
from html import escape
from datetime import datetime, timezone

from matchsignal.database import connect
from matchsignal.scanner import strongest
from matchsignal.config import MODEL_VERSION

app = Flask(__name__)
DATABASE_ENV = os.environ.get("MATCHSIGNAL_DATABASE")
DATABASE = Path(DATABASE_ENV) if DATABASE_ENV else Path(__file__).parent / "data" / "matchsignal.sqlite"

def db():
    if 'database' not in g:
        g.database = connect(DATABASE) if DATABASE and DATABASE.exists() else None
    return g.database


@app.teardown_appcontext
def close_database(error=None):
    connection = g.pop('database', None)
    if connection:
        connection.close()


LAYOUT = """<!doctype html><title>Match Signal</title><meta name=viewport content='width=device-width,initial-scale=1'><style>body{margin:auto;max-width:1080px;padding:28px;background:#08131f;color:#eef5fa;font:16px Arial}a{color:#b8ff4e}nav{display:flex;gap:18px;margin:18px 0 30px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.card{background:#102536;padding:18px;border-radius:8px}small{color:#98aebb;text-transform:uppercase}b{display:block;font-size:1.3em;margin:7px 0}.muted{color:#98aebb}table{width:100%;border-collapse:collapse;margin:12px 0 28px}th,td{border-bottom:1px solid #214154;padding:10px;text-align:left}th{color:#98aebb;font-size:12px;text-transform:uppercase}.pill{display:inline-block;background:#17364c;border-radius:999px;padding:4px 8px}</style><h1>Match Signal</h1><p class=muted>English Football Probability Scanner · Model versions retained in tracker</p><nav><a href='/'>Signals</a><a href='/history'>History</a><a href='/performance'>Performance</a></nav>{{ body|safe }}"""


@app.get("/")
def home():
    if not DATABASE_ENV:
        return send_from_directory('.', 'index.html')
    connection = db()
    if not connection: return send_from_directory(".", "index.html")
    rows = connection.execute("""SELECT p.*,f.home_team,f.away_team,f.competition FROM predictions p JOIN fixtures f ON f.id=p.fixture_id WHERE p.settled_at IS NULL AND p.evidence_status='verified'
        AND f.status='scheduled' AND julianday(f.kickoff)>julianday('now')
        AND p.fixture_kickoff=f.kickoff AND p.model_version=(SELECT model_version FROM prediction_snapshots ORDER BY id DESC LIMIT 1)""").fetchall()
    signals = strongest([{"probability": row["predicted_probability"], "fixture": f"{row['home_team']} vs {row['away_team']}", "selection": row["selection"], "confidence": row["confidence"], "competition": row["competition"]} for row in rows])[:20]
    body = "<h2>Today's strongest signals</h2><div class=grid>" + "".join(f"<article class=card><small>{escape(str(s['competition']))} · {escape(str(s['confidence']))}</small><b>{escape(str(s['fixture']))}</b><p>{escape(str(s['selection']))} · <strong>{s['probability']:.1%}</strong></p></article>" for s in signals) + "</div>" if signals else "<h2>No eligible signals yet</h2><p class=muted>Run the refresh pipeline once historical data and upcoming fixtures are available.</p>"
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
    rows = connection.execute("""SELECT COALESCE(p.fixture_kickoff,f.kickoff) AS kickoff,COALESCE(p.home_team,f.home_team) AS home_team,COALESCE(p.away_team,f.away_team) AS away_team,p.selection,p.predicted_probability,p.correct,p.actual_home_goals,p.actual_away_goals,p.market_group,p.model_version,p.frozen_at FROM predictions p JOIN fixtures f ON f.id=p.fixture_id WHERE p.settled_at IS NOT NULL AND p.evidence_status='verified' AND p.grading_status='settled' ORDER BY kickoff DESC LIMIT 200""").fetchall() if connection else []
    if not rows:
        return render_template_string(LAYOUT, body="<h2>Prediction history</h2><p class=muted>No settled predictions yet.</p>")
    body = "<h2>Prediction history</h2>" + "".join(f"<p>{escape(str(r['kickoff']))} · {escape(str(r['home_team']))} {r['actual_home_goals'] if r['actual_home_goals'] is not None else ''} - {r['actual_away_goals'] if r['actual_away_goals'] is not None else ''} {escape(str(r['away_team']))} · <span class=pill>{escape(r['market_group'] or 'Market')}</span> Model {escape(r['model_version'])} · Frozen {escape(r['frozen_at'])} · {escape(str(r['selection']))} {r['predicted_probability']:.1%} · {'Correct' if r['correct'] else 'Incorrect'}</p>" for r in rows)
    return render_template_string(LAYOUT, body=body)

@app.get('/performance')
def performance():
    return render_template_string(LAYOUT, body=tracker_body(db(), request.args.get('model')))

@app.get('/fixtures/<int:fixture_id>')
def fixture_detail(fixture_id):
    connection = db()
    if not connection: abort(404)
    fixture = connection.execute("SELECT * FROM fixtures WHERE id=?", (fixture_id,)).fetchone()
    if not fixture: abort(404)
    predictions = connection.execute("SELECT selection,predicted_probability,confidence,home_expected_goals,away_expected_goals,model_version,fixture_kickoff FROM predictions WHERE fixture_id=? AND evidence_status='verified' AND snapshot_id=(SELECT id FROM prediction_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1) ORDER BY predicted_probability DESC", (fixture_id, fixture_id)).fetchall()
    body = f"<h2>{escape(str(fixture['home_team']))} vs {escape(str(fixture['away_team']))}</h2><p>{escape(str(fixture['competition']))} · {escape(str(fixture['kickoff']))}</p>"
    if predictions:
        body += f"<p>Model {escape(predictions[0]['model_version'])}; snapshot kickoff {escape(predictions[0]['fixture_kickoff'])}</p><p>Expected goals: {predictions[0]['home_expected_goals']:.2f} – {predictions[0]['away_expected_goals']:.2f}</p>" + "".join(f"<p>{escape(str(p['selection']))}: <b>{p['predicted_probability']:.1%}</b> · {escape(str(p['confidence']))}</p>" for p in predictions)
    return render_template_string(LAYOUT, body=body)


@app.get("/health")
def health():
    deployment = {
        'implementation': 'prospective-tracker-v1',
        'model_version': MODEL_VERSION,
        'commit': os.environ.get('RENDER_GIT_COMMIT') or os.environ.get('MATCHSIGNAL_DEPLOYMENT_SHA'),
    }
    connection = db()
    if not connection:
        return {"status": "no_tracker_database", 'deployment': deployment}, 503
    counts = dict(connection.execute("""SELECT
        COUNT(CASE WHEN evidence_status='verified' THEN 1 END) AS frozen_verified_predictions,
        COUNT(DISTINCT CASE WHEN evidence_status='verified' THEN fixture_id END) AS frozen_fixtures,
        COUNT(CASE WHEN evidence_status='verified' AND grading_status='settled' THEN 1 END) AS settled_predictions,
        COUNT(CASE WHEN evidence_status!='verified' THEN 1 END) AS legacy_unverified_predictions
        FROM predictions""").fetchone())
    latest = connection.execute('SELECT started_at,finished_at,status FROM refresh_runs ORDER BY id DESC LIMIT 1').fetchone()
    if not latest:
        return {"status": "no_refresh_record", 'deployment': deployment, 'tracker': counts}, 503
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(latest['started_at'])).total_seconds()
    healthy = latest['status'] == 'success' and age < 12 * 3600
    return {"status": "ok" if healthy else "tracker_stale_or_failed", "last_refresh": dict(latest),
            'deployment': deployment, 'tracker': counts}, 200 if healthy else 503
