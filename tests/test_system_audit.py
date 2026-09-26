"""Regressions for defects reproduced in the September 2026 system audit."""
from datetime import datetime, timezone, timedelta, date
from html import escape
import json
import pytest
import requests
from matchsignal.database import connect
from matchsignal.fixtures import TheSportsDBProvider, Fixture, upsert_fixtures
from matchsignal.ingestion import import_season, normalize_training_names, parse_csv
from matchsignal.normalization import canonical_team
from matchsignal.service import generate_pending_predictions
from matchsignal.health import refresh_health
from matchsignal.persistence import settle_predictions
from scripts.build_snapshot_v2 import match_day, fixture_window, build_winner_entries
from test_database import seed, forecast, final_result


@pytest.mark.parametrize('source,canonical', [('Accrington','Accrington Stanley'),('Oldham','Oldham Athletic'),('Boston Utd','Boston United'),('Carlisle','Carlisle United'),('Solihull','Solihull Moors'),('Aldershot','Aldershot Town'),('Scunthorpe','Scunthorpe United'),('Yeovil','Yeovil Town'),('Fylde','AFC Fylde'),('Newport County AFC','Newport County'),('FC Halifax','FC Halifax Town')])
def test_observed_team_aliases(source, canonical):
    assert canonical_team(source) == canonical


class Response:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass
    def json(self): return json.loads(self.text)

class Session:
    def __init__(self, text): self.text = text
    def get(self, *args, **kwargs): return Response(self.text)


def test_training_identity_repair_preserves_rows(tmp_path):
    db=connect(tmp_path/'db.sqlite')
    db.execute("INSERT INTO matches_v2(competition,season,kickoff,home_team,away_team,home_goals,away_goals,completed) VALUES('League Two','2026/2027','2026-09-01','Accrington','Oldham',2,1,1)")
    db.commit(); normalize_training_names(db); normalize_training_names(db)
    row=db.execute('SELECT * FROM matches_v2').fetchone()
    assert (row['id'],row['home_team'],row['away_team'],row['home_goals']) == (1,'Accrington Stanley','Oldham Athletic',2)
    assert db.execute('SELECT COUNT(*) FROM matches_v2').fetchone()[0] == 1


@pytest.mark.parametrize('text', ['<html>temporarily unavailable</html>', '', 'Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n'])
def test_success_http_with_no_valid_csv_is_failure(tmp_path,text):
    diagnostics=[];db=connect(tmp_path/'db.sqlite')
    assert import_season(db,2026,Session(text),diagnostics)==0
    assert len(diagnostics)==5 and all(d['status']=='failed' for d in diagnostics)
    assert db.execute('SELECT COUNT(*) FROM matches_v2').fetchone()[0]==0


def event(league='EFL League Two', postponed=False):
    return {'id':'observed-id','competition':{'name':{'full':league}},'start':{'time':'15:00'},
            'teams':{'home':{'name':{'full':'Newport County AFC'}},'away':{'name':{'full':'Grimsby Town'}}},
            'isFixture':not postponed,'isPostponed':postponed}


@pytest.mark.parametrize('league', ['EFL Championship','EFL League One','EFL League Two','National League'])
def test_current_sky_competition_names(league):
    provider=TheSportsDBProvider(Session('<div data-state="'+escape(json.dumps(event(league)),quote=True)+'"></div>'))
    rows=provider._sky_fixtures(datetime(2026,9,26),datetime(2026,9,26,23,59))
    assert len(rows)==1 and rows[0].kickoff=='2026-09-26T14:00:00+00:00'
    assert rows[0].home_team=='Newport County'
    assert provider.diagnostics[0]['status']=='success'


def test_sky_postponement_updates_existing_provider_identity(tmp_path):
    db=connect(tmp_path/'db.sqlite')
    upsert_fixtures(db,[Fixture('fwp-original','League Two','2099-09-26T14:00:00+00:00','Newport County','Grimsby Town')])
    provider=TheSportsDBProvider(Session('<div data-state="'+escape(json.dumps(event(postponed=True)),quote=True)+'"></div>'))
    rows=provider._sky_fixtures(datetime(2099,9,26),datetime(2099,9,26,23,59))
    upsert_fixtures(db,rows)
    assert db.execute('SELECT status FROM fixtures').fetchone()[0]=='postponed'
    assert db.execute('SELECT COUNT(*) FROM fixtures').fetchone()[0]==1


def test_explicit_status_wins_deduplication():
    a=Fixture('one','League Two','2099-09-26T14:00:00+00:00','A','B')
    b=Fixture('two','League Two',a.kickoff,'A','B','postponed')
    assert TheSportsDBProvider._dedupe([a,b])==[b]


def test_broken_html_and_invalid_json_not_valid_empty_schedule():
    provider=TheSportsDBProvider(Session('<html>new layout</html>'))
    assert provider._sky_fixtures(datetime(2026,9,26),datetime(2026,9,26))==[]
    assert provider.covered_competitions()==set()
    assert provider._thesportsdb_fixtures(datetime(2026,9,26),datetime(2026,9,27),{'1':'Premier League'})==[]
    assert provider.diagnostics[-1]['status']=='invalid'


def test_missing_team_history_never_freezes_baseline_only_prediction(tmp_path):
    db=connect(tmp_path/'db.sqlite');seed(db);diagnostics=[]
    assert generate_pending_predictions(db,diagnostics=diagnostics)==0
    assert diagnostics[0]['missing_teams']==['A','B']
    assert db.execute('SELECT COUNT(*) FROM prediction_snapshots').fetchone()[0]==0


def test_failed_league_source_blocks_new_freezes_even_with_cached_history(tmp_path):
    db=connect(tmp_path/'db.sqlite');seed(db)
    db.execute("INSERT INTO matches_v2(competition,season,kickoff,home_team,away_team,home_goals,away_goals,completed,source) VALUES('Premier League','2025','2025-01-01','A','B',1,0,1,'football-data')");db.commit()
    assert generate_pending_predictions(db,eligible_competitions=set())==0
    assert generate_pending_predictions(db,eligible_competitions={'Premier League'})==7


def test_completed_fixture_state_and_withdrawal(tmp_path,monkeypatch):
    from matchsignal.persistence import persist_prediction,record_result
    db=connect(tmp_path/'db.sqlite');persist_prediction(db,seed(db),forecast())
    final_result(db,monkeypatch);assert settle_predictions(db)==7
    assert db.execute('SELECT status FROM fixtures').fetchone()[0]=='completed'
    assert settle_predictions(db)==0
    record_result(db,{'competition':'Premier League','kickoff':'2099-08-01','home_team':'A','away_team':'B','home_goals':None,'away_goals':None,'completed':0},'football-data')
    settle_predictions(db)
    assert db.execute('SELECT status FROM fixtures').fetchone()[0]=='scheduled'


def test_fresh_stale_failed_and_degraded_are_distinct(tmp_path):
    db=connect(tmp_path/'db.sqlite');now=datetime.now(timezone.utc)
    for status,age,expected in [('success',0,'fresh'),('success',13,'stale'),('failed',0,'failed'),('degraded',0,'degraded')]:
        db.execute('INSERT INTO refresh_runs(started_at,finished_at,status,details) VALUES(?,?,?,?)',((now-timedelta(hours=age)).isoformat(),now.isoformat(),status,'{}'));db.commit()
        assert refresh_health(db)['status']==expected
    assert refresh_health(db)['last_success'] is not None


def test_negative_optional_statistics_are_missing_not_zero():
    rows=parse_csv('Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS\n01/09/2026,A,B,1,0,H,-1\n','Premier League','2026/2027')
    assert rows[0]['home_shots'] is None


def test_calendar_filters_use_uk_midnight():
    assert match_day('2026-09-25T23:30:00+00:00')=='2026-09-26'
    assert fixture_window(date(2026,9,26))[0]=='2026-09-25T23:00:00+00:00'


def test_frozen_low_sample_warning_and_mobile_kickoff():
    markets={m:{'predicted_probability':p,'sample':0} for m,p in [('home_win',.5),('draw',.3),('away_win',.2)]}
    output=build_winner_entries({('2099-09-26T14:00:00+00:00','League Two','A','B'):markets})
    assert 'Limited team data when frozen' in output and 'class=mobile-time' in output
    assert 'data-kickoff="2099-09-26T14:00:00+00:00"' in output

@pytest.mark.parametrize('mean', [float('nan'),float('inf'),-1,10000])
def test_invalid_or_unrepresentable_goal_means_fail_explicitly(mean):
    from matchsignal.poisson import score_matrix
    with pytest.raises(ValueError): score_matrix(mean,1)


def test_failure_record_survives_restart(tmp_path,monkeypatch):
    from scripts import refresh_v2
    path=tmp_path/'db.sqlite';connect(path).close()
    monkeypatch.setattr(refresh_v2,'DATABASE',path)
    def fail(db): raise RuntimeError('injected source failure')
    monkeypatch.setattr(refresh_v2,'refresh',fail)
    with pytest.raises(RuntimeError,match='injected'):refresh_v2.main()
    db=connect(path)
    assert refresh_health(db)['status']=='failed'


def test_partial_failure_record_survives_restart(tmp_path,monkeypatch):
    from scripts import refresh_v2
    path=tmp_path/'db.sqlite';connect(path).close()
    monkeypatch.setattr(refresh_v2,'DATABASE',path)
    monkeypatch.setattr(refresh_v2,'refresh',lambda db: {'status':'degraded','leagues':{'League Two':{'statistics':'failed'}}})
    refresh_v2.main();db=connect(path)
    assert refresh_health(db)['status']=='degraded'
    assert refresh_health(db)['leagues']['League Two']['statistics']=='failed'
