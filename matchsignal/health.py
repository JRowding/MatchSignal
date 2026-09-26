"""Read-only refresh state shared by API and dashboard."""
import json
from .timeutils import utc_now, instant


def refresh_health(connection):
    latest = connection.execute('SELECT * FROM refresh_runs ORDER BY id DESC LIMIT 1').fetchone()
    success = connection.execute("SELECT finished_at FROM refresh_runs WHERE status='success' ORDER BY id DESC LIMIT 1").fetchone()
    if not latest:
        return {'status': 'no_refresh_record', 'last_success': None, 'leagues': {}}
    try:
        details = json.loads(latest['details'] or '{}')
    except (ValueError, TypeError):
        details = {'error': latest['details']}
    age = (utc_now() - instant(latest['started_at'])).total_seconds()
    state = latest['status']
    status = 'stale' if age >= 12 * 3600 else 'fresh' if state == 'success' else state
    return {'status': status, 'last_refresh': dict(latest),
            'last_success': success['finished_at'] if success else None,
            'leagues': details.get('leagues', {}), 'age_seconds': round(age),
            'source_warnings': [s for s in details.get('sources', []) if s.get('status') != 'success']}
