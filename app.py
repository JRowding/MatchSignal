"""Read-only scanner app. External data is refreshed by the scheduled job."""
import os
from flask import Flask, jsonify
from matchsignal.dashboard import render_dashboard
from matchsignal.refresh import SNAPSHOT, current_view, read_snapshot
app = Flask(__name__)

@app.get('/')
def home():
    return render_dashboard(read_snapshot(SNAPSHOT))

@app.get('/api/signals')
def signals():
    return jsonify(current_view(read_snapshot(SNAPSHOT)))

@app.get('/health')
def health():
    view = current_view(read_snapshot(SNAPSHOT))
    return {'status': view['status'], 'leagues_checked': view.get('leagues_checked', 0),
            'last_successful_refresh': view.get('last_successful_refresh'),
            'last_attempt': view.get('refreshed_at'),
            'implementation': 'top-bottom-mismatch-scanner',
            'commit': os.environ.get('RENDER_GIT_COMMIT') or os.environ.get('MATCHSIGNAL_DEPLOYMENT_SHA')}, 200 if view['status'] == 'ok' else 503
