"""Existing dark/lime identity, UK kickoff formatting and calendar navigation."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .config import CONFIG, CACHE_MAX_AGE_HOURS, SIGNAL_PERCENTAGE
from .leagues import LEAGUES
from .refresh import ROOT, current_view
from .timeutils import instant, utc_now


def match_time(value):
    kickoff = instant(str(value)).astimezone(ZoneInfo('Europe/London'))
    hour = kickoff.hour % 12 or 12
    minute = f':{kickoff.minute:02d}' if kickoff.minute else ''
    suffix = 'am' if kickoff.hour < 12 else 'pm'
    return f"{kickoff.strftime('%A')} {hour}{minute}{suffix}"


def match_day(value):
    return instant(str(value)).astimezone(ZoneInfo('Europe/London')).date().isoformat()


def full_date(value):
    return instant(value).astimezone(ZoneInfo('Europe/London')).strftime('%A %d %B %Y')


def ordinal(n):
    return str(n) + ('th' if 10 <= n % 100 <= 20 else {1:'st', 2:'nd', 3:'rd'}.get(n % 10, 'th'))


def render_dashboard(snapshot, now=None):
    now = now or utc_now()
    view = current_view(snapshot, now)
    today = now.astimezone(ZoneInfo('Europe/London')).date()
    days = [today + timedelta(days=i) for i in range(CONFIG.fixture_lookahead_days + 1)]
    env = Environment(loader=FileSystemLoader(ROOT / 'templates'), autoescape=select_autoescape(['html']))
    env.globals.update(match_time=match_time, match_day=match_day, full_date=full_date, ordinal=ordinal)
    return env.get_template('dashboard.html').render(view=view, days=days, today=today, leagues=LEAGUES,
           percentage=round(snapshot.get('percentage', SIGNAL_PERCENTAGE)*100), expiry_hours=CACHE_MAX_AGE_HOURS)


def validation_report(snapshot):
    lines = ['# MatchSignal live validation', '', f"Refresh: {snapshot['refreshed_at']}",
             f"Window: {snapshot['window_start']} through {snapshot['window_end']} (Europe/London).",
             f"{snapshot['leagues_checked']}/11 leagues checked; {len(snapshot['signals'])} qualifying fixtures.", '',
             'Counts below reflect the refresh instant; already-started matches disappear from the app.', '',
             '| League | Table | Fixtures | Teams | Top | Bottom | Checked | Signals | Source | Last success |',
             '|---|---|---|---:|---:|---:|---:|---:|---|---|']
    for name, state in snapshot['leagues'].items():
        source = (state.get('table') or {}).get('source', 'unavailable')
        lines.append('| ' + ' | '.join(str(x) for x in [name, state['table_status'], state['fixture_status'],
            state['team_count'], state['top_count'], state['bottom_count'], state['fixtures_evaluated'],
            state['signals_found'], source, state['last_successful_refresh'] or 'never']) + ' |')
    lines += ['', '## Qualifying fixtures', '', '| Day/date | UK kickoff | League | Home | Away | Top | Bottom |', '|---|---|---|---|---|---|---|']
    for f in snapshot['signals']:
        lines.append('| ' + ' | '.join([full_date(f['kickoff']), match_time(f['kickoff']), f['competition'],
            f"{f['home_team']} ({ordinal(f['home_position'])})", f"{f['away_team']} ({ordinal(f['away_position'])})",
            f['top_team'], f['bottom_team']]) + ' |')
    lines += ['', '## Source diagnostics', '']
    for name, s in snapshot['leagues'].items():
        lines += [f"### {name}", f"Fallback used: {s['fallback_used']}. Publisher table timestamp: {(s.get('table') or {}).get('publisher_updated')}.",
                  f"Fixture sources: {(s.get('fixtures') or {}).get('sources', [])}.",
                  f"Errors: {s['errors'] or 'none'}. Unmatched: {s['unmatched_clubs'] or 'none'}.",
                  f"Source warnings: {s['source_warnings'] or 'none'}.", '']
    lines += ['## Verification scope', '',
        'This report records automated retrieval and validation, not independent confirmation. See REVIEW_VALIDATION.md for independent samples, regression tests and UI checks.',
        'Sky dated pages are the existing all-competition fixture feed. Successful parsing verifies the feed, not an absolute guarantee that the publisher lists every rearrangement. FWP failures remain visible. Tables retain publisher positions, including deductions and split ordering. The source update label is retained separately from our download time.']
    return '\n'.join(lines) + '\n'
