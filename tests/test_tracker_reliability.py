from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import sqlite3
import pytest

import app
from matchsignal.database import connect
from matchsignal.persistence import persist_prediction, settle_predictions
from matchsignal.reporting import tracker_body
from matchsignal.predictor import predict
from matchsignal.count_models import _form
from matchsignal.timeutils import utc_text
from test_database import seed, forecast, final_result


def test_competing_writers_capture_only_one_batch(tmp_path):
    path=tmp_path/'race.sqlite'; db=connect(path); seed(db); db.close()
    def write(_):
        db=connect(path)
        try: return persist_prediction(db, db.execute('SELECT * FROM fixtures').fetchone(), forecast())
        finally: db.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, range(2))) == [0, 7]


def test_mid_batch_failure_rolls_back_header_and_all_markets(tmp_path):
    db=connect(tmp_path/'fail.sqlite'); fixture=seed(db)
    db.execute("CREATE TRIGGER fail_draw BEFORE INSERT ON predictions WHEN NEW.market='draw' BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError): persist_prediction(db, fixture, forecast())
    assert db.execute('SELECT COUNT(*) FROM prediction_snapshots').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0] == 0


def test_clock_crossing_rolls_back(tmp_path, monkeypatch):
    db=connect(tmp_path/'clock.sqlite'); fixture=seed(db)
    real_now=datetime.now(timezone.utc); calls=[]
    def clock():
        calls.append(1)
        return real_now if len(calls)<4 else datetime(2100,1,1,tzinfo=timezone.utc)
    monkeypatch.setattr('matchsignal.persistence.utc_now', clock)
    with pytest.raises(ValueError, match='Kickoff crossed'): persist_prediction(db,fixture,forecast())
    assert db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0] == 0


def test_dashboard_measures_picks_and_filters_models(tmp_path, monkeypatch):
    path=tmp_path/'ui.sqlite'; db=connect(path); fixture=seed(db)
    persist_prediction(db, fixture, forecast())
    alternative=forecast(); alternative['model_version']='B'; alternative['probabilities']['home_win']=.1
    alternative['probabilities']['away_win']=.72
    persist_prediction(db, fixture, alternative)
    final_result(db, monkeypatch); settle_predictions(db)
    body=tracker_body(db, '2.5.1')
    assert '4</td><td>1</td><td>100.0%' in body
    assert 'probability forecasts' in body and 'log loss' in body
    assert '50.0%' not in body.split('Overall displayed picks')[1].split('</table>')[0]
    assert 'No verified predictions' in tracker_body(db,'does-not-exist')
    db.close(); monkeypatch.setattr(app,'DATABASE',path)
    client=app.app.test_client()
    for route in ('/','/performance?model=2.5.1','/history','/fixtures/1'):
        response=client.get(route)
        assert response.status_code==200
    assert client.get('/health').status_code==503


def test_legacy_migration_does_not_invent_provenance(tmp_path):
    path=tmp_path/'legacy.sqlite'; db=sqlite3.connect(path)
    db.executescript('''CREATE TABLE fixtures(id INTEGER PRIMARY KEY,external_fixture_id TEXT UNIQUE,competition TEXT,kickoff TEXT,home_team TEXT,away_team TEXT,status TEXT);
        INSERT INTO fixtures VALUES(1,'old','Premier League','2020-01-01','A','B','completed');
        CREATE TABLE predictions(id INTEGER PRIMARY KEY,fixture_id INTEGER,prediction_created_at TEXT,model_version TEXT,
        home_expected_goals REAL,away_expected_goals REAL,market TEXT,selection TEXT,predicted_probability REAL,
        confidence TEXT,actual_outcome INTEGER,correct INTEGER,settled_at TEXT);
        INSERT INTO predictions VALUES(1,1,'2020-01-02','old',1,1,'home_win','Home win',.9,'HIGH',1,1,'2020-01-03');''')
    db.close(); db=connect(path)
    row=db.execute('SELECT * FROM predictions').fetchone()
    assert row['evidence_status']=='legacy_unverified' and row['frozen_at'] is None
    assert 'excluded: 1' in tracker_body(db)


def test_missing_results_visible_and_no_result_source_guessing(tmp_path,monkeypatch):
    db=connect(tmp_path/'missing.sqlite'); persist_prediction(db,seed(db),forecast())
    monkeypatch.setattr('matchsignal.persistence.utc_now',lambda:datetime(2099,8,3,tzinfo=timezone.utc))
    assert settle_predictions(db)==0
    assert 'missing results: 7' in tracker_body(db)


def test_same_day_and_future_results_cannot_affect_backtest():
    past={'competition':'Premier League','kickoff':'2025-01-01','home_team':'A','away_team':'B','home_goals':1,'away_goals':0}
    future={**past,'kickoff':'2025-01-02','home_goals':99}
    kickoff=datetime(2025,1,2,15,tzinfo=timezone.utc)
    assert predict([past], 'Premier League','A','B',kickoff)==predict([past,future], 'Premier League','A','B',kickoff)


def test_away_count_form_uses_only_the_away_team():
    matches=[{'kickoff':'2025-01-01','home_team':'X','away_team':'B','home_shots':10,'away_shots':8},
             {'kickoff':'2025-01-02','home_team':'X','away_team':'C','home_shots':10,'away_shots':99}]
    form=_form(matches,'B',datetime(2025,2,1),False,'shots')
    assert form['sample']==1 and form['for']==8


def test_uk_summer_and_winter_time_are_explicit():
    assert utc_text('2026-08-01T15:00:00','Europe/London')=='2026-08-01T14:00:00+00:00'
    assert utc_text('2026-12-01T15:00:00','Europe/London')=='2026-12-01T15:00:00+00:00'


def test_withdrawn_final_result_clears_grade(tmp_path,monkeypatch):
    from matchsignal.persistence import record_result
    db=connect(tmp_path/'withdrawn.sqlite'); persist_prediction(db,seed(db),forecast())
    final_result(db,monkeypatch); settle_predictions(db)
    record_result(db,{'competition':'Premier League','kickoff':'2099-08-01','home_team':'A','away_team':'B',
                      'home_goals':None,'away_goals':None,'completed':0},'football-data')
    settle_predictions(db)
    row=db.execute('SELECT * FROM predictions').fetchone()
    assert row['actual_outcome'] is None and row['grading_status']=='result_withdrawn'


def test_conflicting_kickoff_is_not_silently_cleared_on_next_poll(tmp_path):
    from matchsignal.fixtures import Fixture, upsert_fixtures
    db=connect(tmp_path/'conflict.sqlite'); seed(db)
    upsert_fixtures(db,[Fixture('other','Premier League','2099-08-01T16:00:00+00:00','A','B')])
    seed(db)
    assert db.execute('SELECT status FROM fixtures').fetchone()[0]=='identity_conflict'


def test_sql_replace_cannot_bypass_immutability(tmp_path):
    db=connect(tmp_path/'replace.sqlite'); persist_prediction(db,seed(db),forecast())
    with pytest.raises(sqlite3.IntegrityError,match='immutable'):
        db.execute('INSERT OR REPLACE INTO prediction_snapshots SELECT * FROM prediction_snapshots')
    db.rollback()
    assert db.execute('SELECT COUNT(*) FROM prediction_snapshots').fetchone()[0]==1
