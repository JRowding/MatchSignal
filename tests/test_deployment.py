from datetime import datetime, timezone

import app
from matchsignal.database import connect
from matchsignal.config import MODEL_VERSION


def test_health_reports_revision_counts_and_real_refresh_state(tmp_path, monkeypatch):
    path = tmp_path / 'deployment.sqlite'
    db = connect(path)
    db.execute("INSERT INTO refresh_runs(started_at,finished_at,status) VALUES(?,?,'success')",
               (datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
    db.commit(); db.close()
    monkeypatch.setattr(app, 'DATABASE', path)
    monkeypatch.setenv('RENDER_GIT_COMMIT', 'deployed-revision')
    response = app.app.test_client().get('/health')
    assert response.status_code == 200
    assert response.json['deployment']['commit'] == 'deployed-revision'
    assert response.json['deployment']['model_version'] == MODEL_VERSION
    assert response.json['tracker'] == {'frozen_verified_predictions': 0, 'frozen_fixtures': 0,
                                        'settled_predictions': 0, 'legacy_unverified_predictions': 0}
    db = connect(path)
    db.execute("UPDATE refresh_runs SET status='failed'"); db.commit(); db.close()
    assert app.app.test_client().get('/health').status_code == 503


def test_existing_static_tabs_and_preview_still_work(monkeypatch):
    monkeypatch.setattr(app, 'DATABASE_ENV', None)
    client = app.app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    for label in (b'Over 2.5 Goals', b'Match Winners', b'Both Teams to Score', b'BTTS + Winner'):
        assert label in response.data
    assert client.get('/mockup').status_code == 200
