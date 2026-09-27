from copy import deepcopy
from datetime import timedelta
from dataclasses import replace
import json
import pytest
from matchsignal.refresh import refresh, current_view, atomic_write, read_snapshot
from matchsignal.leagues import LEAGUES
from matchsignal.dashboard import render_dashboard
from test_mismatch import NOW, fixture, table

class Fixtures:
    diagnostics=[{'source':'sky','scope':'2026-09-27','status':'success','rows':1}]
    def upcoming(self):return [fixture()]
    def covered_competitions(self):return {l.name for l in LEAGUES}

class Tables:
    def table(self,l):return {'rows':table(), 'source':'https://example.test', 'publisher_updated':'Today'}

class FailedTables(Tables):
    def table(self,l):
        if l.name=='Premier League':raise ValueError('Source down')
        return super().table(l)

def fresh():return refresh(provider=Fixtures(),table_provider=Tables(),now=NOW)

def test_all_leagues_and_valid_zero_fixtures():
    s=fresh()
    assert s['leagues_checked']==11 and len(s['signals'])==1
    assert s['leagues']['Scottish League Two']['checked']
    assert s['leagues']['Scottish League Two']['signals_found']==0

def test_failure_isolated_cache_bounded_not_refreshed():
    s=fresh()
    result=refresh(s,provider=Fixtures(),table_provider=FailedTables(),now=NOW+timedelta(hours=1))
    assert result['leagues_checked']==10 and result['status']=='degraded'
    assert result['signals'][0]['cached']
    assert result['leagues']['Premier League']['table']['refreshed_at']==NOW.isoformat()
    expired=refresh(result,provider=Fixtures(),table_provider=FailedTables(),now=NOW+timedelta(hours=13))
    assert expired['leagues']['Premier League']['table_status']=='unavailable'
    assert not expired['signals']

def test_new_window_does_not_claim_old_fixture_cache_covers_it():
    class FailedFixtures(Fixtures):
        def covered_competitions(self):return set()
    s=refresh(fresh(),provider=FailedFixtures(),table_provider=Tables(),now=NOW+timedelta(hours=17))
    assert not s['signals'] and s['leagues_checked']==0

def test_view_expires_and_hides_started_fixtures():
    assert not current_view(fresh(),NOW+timedelta(hours=13))['signals']
    s=fresh();s['signals'][0]['kickoff']=NOW.isoformat()
    assert not current_view(s,NOW)['signals']

def test_atomic_snapshot_roundtrip_and_corrupt_file(tmp_path):
    p=tmp_path/'signals.json';atomic_write(p,json.dumps(fresh()))
    assert read_snapshot(p)['status']=='ok'
    p.write_text('{broken');assert read_snapshot(p)['status']=='unavailable'

def test_display_dates_positions_escape_and_no_predictions():
    s=fresh();s['signals'][0]['home_team']='<script>alert(1)</script>';s['signals'][0]['top_team']=s['signals'][0]['home_team']
    html=render_dashboard(s,NOW)
    assert '&lt;script&gt;' in html and 'Tuesday 29 September 2026' in html
    assert 'Tuesday 7:45pm' in html and '20th' in html and 'TOP 30%' in html
    assert 'data-day="2026-09-29"' in html
    assert 'Prediction Tracker' not in html and 'probability' not in html

def test_health_and_home_do_not_fetch_network(tmp_path,monkeypatch):
    import app
    p=tmp_path/'signals.json';atomic_write(p,json.dumps(fresh()))
    monkeypatch.setattr(app,'SNAPSHOT',p)
    monkeypatch.setattr('requests.get',lambda *a,**kw:pytest.fail('Page request fetched a feed'))
    with app.app.test_client() as c:
        assert c.get('/').status_code==200
        assert c.get('/api/signals').status_code==200
        assert c.get('/history').status_code==404
        assert c.get('/performance').status_code==404
        p.unlink();assert c.get('/health').status_code==503

def test_expired_individual_cache_changes_display_status():
    s=fresh();s['leagues']['Premier League']['table']['refreshed_at']=(NOW-timedelta(hours=13)).isoformat()
    v=current_view(s,NOW)
    assert v['status']=='degraded' and v['leagues_checked']==10 and not v['signals']
    assert v['leagues']['Premier League']['table_status']=='unavailable'

def test_unexpected_provider_failure_still_emits_all_leagues():
    class Broken(Fixtures):
        def upcoming(self):raise RuntimeError('Malformed response')
    s=refresh(provider=Broken(),table_provider=Tables(),now=NOW)
    assert len(s['leagues'])==11 and s['status']=='degraded'
    assert all(state['errors'] for state in s['leagues'].values())
