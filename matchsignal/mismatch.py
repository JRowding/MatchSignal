"""Pure same-league top/bottom matching using explicit publisher positions."""
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import asdict
from .config import SIGNAL_PERCENTAGE
from .normalization import canonical_team, team_key
from .standings import validate_table
from .timeutils import instant


def group_size(team_count, percentage=SIGNAL_PERCENTAGE):
    if not 0 < percentage <= .5:
        raise ValueError('Signal percentage must be greater than zero and at most 0.5')
    count = int((Decimal(team_count) * Decimal(str(percentage))).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    if count < 1 or 2 * count > team_count:
        raise ValueError('Percentage creates empty or overlapping groups')
    return count


def scan(league, table, fixtures, now, end):
    rows = validate_table(table)
    size = group_size(len(rows))
    positions = {team_key(canonical_team(r['team'])): r['position'] for r in rows}
    signals, unmatched, conflicts = [], set(), []
    evaluated = 0
    buckets = {}
    for fixture in fixtures:
        if fixture.competition != league:
            continue
        key = (team_key(canonical_team(fixture.home_team)), team_key(canonical_team(fixture.away_team)))
        buckets.setdefault(key, []).append(fixture)
    for key, candidates in buckets.items():
        relevant = [f for f in candidates if now < instant(f.kickoff) < end]
        if not relevant:
            continue
        if any(f.status != 'scheduled' for f in relevant):
            continue
        if len({f.kickoff for f in relevant}) > 1:
            conflicts.append(f'{relevant[0].home_team} vs {relevant[0].away_team}: conflicting kickoff times')
            continue
        fixture = relevant[0]
        home, away = positions.get(key[0]), positions.get(key[1])
        if home is None: unmatched.add(fixture.home_team)
        if away is None: unmatched.add(fixture.away_team)
        if home is None or away is None or key[0] == key[1]:
            continue
        evaluated += 1
        bottom_start = len(rows) - size + 1
        if (home <= size and away >= bottom_start) or (away <= size and home >= bottom_start):
            signals.append({**asdict(fixture), 'home_position': home, 'away_position': away,
                            'top_team': fixture.home_team if home <= size else fixture.away_team,
                            'bottom_team': fixture.away_team if home <= size else fixture.home_team,
                            'team_count': len(rows), 'group_size': size})
    return sorted(signals, key=lambda f: (instant(f['kickoff']), f['competition'], f['home_team'])), {
        'team_count': len(rows), 'top_count': size, 'bottom_count': size,
        'fixtures_evaluated': evaluated, 'unmatched_clubs': sorted(unmatched), 'conflicts': conflicts,
        'signals_found': len(signals)}
