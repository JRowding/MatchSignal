"""Scheduled snapshot refresh; page requests never trigger upstream requests."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timedelta
import json
import logging
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import CONFIG, CACHE_MAX_AGE_HOURS, SIGNAL_PERCENTAGE
from .fixtures import Fixture, TheSportsDBProvider
from .leagues import LEAGUES
from .mismatch import scan, group_size
from .standings import StandingsProvider
from .timeutils import instant, utc_now

LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = Path(os.environ.get('MATCHSIGNAL_SNAPSHOT', ROOT / 'data' / 'signals.json'))


def read_snapshot(path=SNAPSHOT):
    try:
        data = json.loads(Path(path).read_text())
        if data.get('schema_version') != 1 or not isinstance(data.get('leagues'), dict):
            raise ValueError('Unknown scanner snapshot schema')
        return data
    except (OSError, ValueError):
        return {'schema_version': 1, 'leagues': {}, 'signals': [], 'status': 'unavailable'}


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(text)
    temp.replace(path)


def cache_valid(record, now):
    try:
        age = (now - instant(record['refreshed_at'])).total_seconds()
        return 0 <= age < CACHE_MAX_AGE_HOURS * 3600
    except (KeyError, TypeError, ValueError):
        return False


def refresh(previous=None, provider=None, table_provider=None, now=None):
    now = now or utc_now()
    previous = previous or {}
    provider = provider or TheSportsDBProvider()
    table_provider = table_provider or StandingsProvider()
    today = now.astimezone(ZoneInfo('Europe/London')).date()
    end = instant(datetime.combine(today + timedelta(days=CONFIG.fixture_lookahead_days + 1), datetime.min.time()), 'Europe/London')
    start_text, end_text = today.isoformat(), (today + timedelta(days=CONFIG.fixture_lookahead_days)).isoformat()
    try:
        incoming = provider.upcoming()
        covered = provider.covered_competitions()
        diagnostics = provider.diagnostics
    except Exception as exc:
        LOG.exception('Fixture collection failed')
        incoming, covered = [], set()
        diagnostics = [{'source': 'sky', 'scope': 'all', 'status': 'failed', 'rows': 0, 'error': str(exc)}]
    def fetch_table(league):
        try:
            return league.name, table_provider.table(league), None
        except Exception as exc:
            LOG.warning('Table failed for %s: %s', league.name, exc)
            return league.name, None, str(exc)
    with ThreadPoolExecutor(max_workers=4) as pool:
        tables = {name: (table, error) for name, table, error in pool.map(fetch_table, LEAGUES)}
    result = {'schema_version': 1, 'percentage': SIGNAL_PERCENTAGE, 'refreshed_at': now.isoformat(),
              'window_start': start_text, 'window_end': end_text, 'leagues': {}, 'signals': [],
              'fixture_sources': diagnostics, 'last_successful_refresh': previous.get('last_successful_refresh')}
    for league in LEAGUES:
        name = league.name
        old = previous.get('leagues', {}).get(name, {})
        table, error = tables[name]
        state = {'table_status': 'live' if table else 'unavailable',
                 'fixture_status': 'live' if name in covered else 'unavailable',
                 'errors': [error] if error else [], 'unmatched_clubs': [], 'conflicts': [],
                 'team_count': None, 'top_count': None, 'bottom_count': None,
                 'fixtures_evaluated': 0, 'signals_found': 0, 'last_successful_refresh': old.get('last_successful_refresh')}
        if table:
            table = {**table, 'refreshed_at': now.isoformat()}
        else:
            cached = old.get('table')
            if cached and cache_valid(cached, now):
                table = cached
                state['table_status'] = 'cached'
        relevant = [d for d in diagnostics if d['scope'] == name or d['source'] == 'sky']
        state['source_warnings'] = [d for d in relevant if d['status'] != 'success' or name in d.get('invalid_competitions', [])]
        live_fixtures = [f for f in incoming if f.competition == name]
        fixture_data = None
        if name in covered:
            sources = sorted({d['source'] for d in relevant if d['status'] == 'success'})
            fixture_data = {'rows': [asdict(f) for f in live_fixtures], 'refreshed_at': now.isoformat(),
                            'window_start': start_text, 'window_end': end_text, 'sources': sources}
        else:
            state['errors'].append('Fixture feed coverage could not be verified')
            cached = old.get('fixtures')
            if (cached and cache_valid(cached, now) and cached.get('window_start', '9999') <= start_text
                    and cached.get('window_end', '') >= end_text):
                fixture_data = cached
                state['fixture_status'] = 'cached'
        # Keep last-good records even when expired; never relabel them as fresh.
        state['table'] = table or old.get('table')
        state['fixtures'] = fixture_data or old.get('fixtures')
        state['fixtures_retrieved'] = len(fixture_data['rows']) if fixture_data else 0
        state['fallback_used'] = (state['table_status'] == 'cached' or state['fixture_status'] == 'cached'
                                  or 'fwp' in (fixture_data or {}).get('sources', []))
        if table:
            size = group_size(len(table['rows']))
            state.update(team_count=len(table['rows']), top_count=size, bottom_count=size)
        if table and fixture_data:
            try:
                signals, counts = scan(name, table['rows'], [Fixture(**f) for f in fixture_data['rows']], now, end)
                state.update(counts)
                state['errors'].extend(counts['conflicts'])
                if counts['unmatched_clubs']:
                    state['errors'].append('Unmatched clubs: ' + ', '.join(counts['unmatched_clubs']))
                for signal in signals:
                    signal['cached'] = state['table_status'] == 'cached' or state['fixture_status'] == 'cached'
                    signal['valid_until'] = (min(instant(table['refreshed_at']), instant(fixture_data['refreshed_at'])) + timedelta(hours=CACHE_MAX_AGE_HOURS)).isoformat()
                result['signals'].extend(signals)
            except (ValueError, TypeError, KeyError) as exc:
                state['errors'].append(str(exc))
        state['checked'] = state['table_status'] == state['fixture_status'] == 'live' and not state['errors']
        if state['checked']:
            state['last_successful_refresh'] = now.isoformat()
        for message in state['errors']:
            LOG.warning('%s: %s', name, message)
        result['leagues'][name] = state
    result['signals'].sort(key=lambda f: (instant(f['kickoff']), f['competition'], f['home_team']))
    result['leagues_checked'] = sum(s['checked'] for s in result['leagues'].values())
    result['status'] = 'ok' if result['leagues_checked'] == len(LEAGUES) else 'degraded'
    if result['status'] == 'ok':
        result['last_successful_refresh'] = now.isoformat()
    return result


def current_view(snapshot, now=None):
    """Hide kicked-off/expired signals even between scheduled refreshes."""
    now = now or utc_now()
    view = {**snapshot, 'leagues': {name: dict(state) for name, state in snapshot.get('leagues', {}).items()}}
    for state in view['leagues'].values():
        for kind, record in [('table', 'table'), ('fixture', 'fixtures')]:
            if not cache_valid(state.get(record) or {}, now):
                state[kind + '_status'] = 'unavailable'
                state['checked'] = False
    view['leagues_checked'] = sum(s.get('checked', False) for s in view['leagues'].values())
    if view['leagues_checked'] != len(LEAGUES) and view.get('status') == 'ok':
        view['status'] = 'degraded'
    fresh = cache_valid(snapshot, now)
    if not fresh:
        view['status'] = 'stale' if snapshot.get('refreshed_at') else 'unavailable'
        view['leagues_checked'] = 0
    view['signals'] = [f for f in snapshot.get('signals', []) if fresh and instant(f['kickoff']) > now
                       and cache_valid(snapshot['leagues'][f['competition']].get('table') or {}, now)
                       and cache_valid(snapshot['leagues'][f['competition']].get('fixtures') or {}, now)]
    return view
