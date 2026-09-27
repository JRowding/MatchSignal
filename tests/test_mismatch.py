from datetime import datetime, timezone, timedelta
import pytest
from matchsignal.fixtures import Fixture
from matchsignal.mismatch import group_size, scan
from matchsignal.standings import validate_table
from matchsignal.timeutils import instant
from matchsignal.dashboard import match_time, match_day

NOW = datetime(2026, 9, 27, 8, tzinfo=timezone.utc)
END = NOW + timedelta(days=5)

def table(n=20):
    return [{'team': f'Team {i}', 'position': i, 'played': 5} for i in range(1, n+1)]

def fixture(home=1, away=20, **kwargs):
    return Fixture('test', 'Premier League', kwargs.pop('kickoff', '2026-09-29T18:45:00+00:00'),
                   f'Team {home}', f'Team {away}', **kwargs)

@pytest.mark.parametrize('n,want', [(24,7),(20,6),(12,4),(10,3)])
def test_required_sizes(n,want):
    assert group_size(n)==want

@pytest.mark.parametrize('home,away,qualifies',[(1,20,True),(20,1,True),(6,15,True),(15,6,True),
    (6,14,False),(7,15,False),(1,2,False),(19,20,False),(7,10,False),(1,10,False),(10,20,False)])
def test_exact_boundaries_both_directions(home,away,qualifies):
    signals, state=scan('Premier League',table(),[fixture(home,away)],NOW,END)
    assert len(signals)==int(qualifies)
    assert state['fixtures_evaluated']==1

@pytest.mark.parametrize('status',['postponed','cancelled','abandoned','completed'])
def test_non_upcoming_status_is_excluded(status):
    assert not scan('Premier League',table(),[fixture(status=status)],NOW,END)[0]

def test_unknown_names_and_conflicting_times_not_guessed():
    signals,state=scan('Premier League',table(),[fixture(999,20)],NOW,END)
    assert not signals and state['unmatched_clubs']==['Team 999']
    signals,state=scan('Premier League',table(),[fixture(),fixture(kickoff='2026-09-29T19:45:00+00:00')],NOW,END)
    assert not signals and state['conflicts']

def test_deduplication_order_and_past_fixtures():
    first=fixture(2,19,kickoff='2026-09-28T18:45:00+00:00')
    signals,_=scan('Premier League',table(),[fixture(),first,fixture(),fixture(3,18,kickoff=NOW.isoformat())],NOW,END)
    assert len(signals)==2 and signals[0]['home_team']=='Team 2'

def test_cross_league_fixture_not_evaluated():
    assert scan('Championship',table(),[fixture()],NOW,END)[1]['fixtures_evaluated']==0

def test_bad_tables_rejected():
    for rows in [table()[:7], table()+[table()[0]], table()[:10]+table()[11:]]:
        with pytest.raises(ValueError):validate_table(rows)

def test_summer_winter_midnight_and_dst():
    assert match_time('2026-09-29T18:45:00+00:00')=='Tuesday 7:45pm'
    assert match_time('2026-12-01T19:45:00+00:00')=='Tuesday 7:45pm'
    assert match_day('2026-09-29T23:15:00+00:00')=='2026-09-30'
    assert instant('2026-10-25T15:00:00','Europe/London').hour==15
    assert instant('2026-10-24T15:00:00','Europe/London').hour==14
