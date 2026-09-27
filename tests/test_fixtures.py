from datetime import datetime

from matchsignal.config import CONFIG
from matchsignal.fixtures import TheSportsDBProvider, fixture_window


def test_football_web_pages_time_parser_handles_common_kickoff_times():
    assert TheSportsDBProvider._football_web_pages_kickoff("28/8/2026", "7.45pm") == datetime(2026, 8, 28, 19, 45)
    assert TheSportsDBProvider._football_web_pages_kickoff("31/8/2026", "3pm") == datetime(2026, 8, 31, 15, 0)


def test_sky_provider_uses_configured_timeout():
    class Response:
        text = ""

        def raise_for_status(self):
            return None

    class Session:
        timeout = None

        def get(self, url, timeout, headers):
            self.timeout = timeout
            return Response()

    session = Session()
    TheSportsDBProvider(session)._sky_fixtures(datetime(2026, 8, 29), datetime(2026, 8, 29))
    assert session.timeout == CONFIG.source_timeout_seconds


def test_fixture_window_covers_all_of_today_and_the_next_four_days():
    start, end = fixture_window(datetime(2026, 9, 1, 17, 30))

    assert start == datetime(2026, 9, 1, 0, 0)
    assert end.date().isoformat() == "2026-09-05"
    assert (end.hour, end.minute, end.second) == (23, 59, 59)


def test_fwp_provider_reads_all_supported_competitions():
    html = '''
    <tr data-href="match/example-fixture">
      <td class="d-none export-only">05/09/2026</td>
      <td class="status">3pm</td>
      <td class="team home-team" data-export="Home United"></td>
      <td class="team away-team" data-export="Away City"></td>
    </tr>
    '''

    class Response:
        text = html

        def raise_for_status(self):
            return None

    class Session:
        def get(self, url, params, timeout, headers):
            return Response()

    fixtures = TheSportsDBProvider(Session())._football_web_pages_fixtures(
        datetime(2026, 9, 5, 0, 0),
        datetime(2026, 9, 9, 23, 59, 59),
    )

    competitions = {fixture.competition for fixture in fixtures}
    assert competitions == {
        "Premier League",
        "Championship",
        "League One",
        "League Two",
        "National League",
        "National League North",
        "National League South",
    }


def test_fwp_does_not_borrow_fields_across_rows():
    class Response:
        text = '''<tr data-href="match/wrong-id"><td>No valid fixture fields</td></tr>
        <tr data-href="match/correct-id"><td class="d-none export-only">05/09/2026</td>
        <td class="status">3pm</td><td class="team home-team" data-export="A"></td>
        <td class="team away-team" data-export="B"></td></tr>'''
        def raise_for_status(self): pass
    class Session:
        def get(self, *args, **kwargs): return Response()
    rows=TheSportsDBProvider(Session())._football_web_pages_fixtures(datetime(2026,9,5),datetime(2026,9,6))
    assert len(rows)==7
    assert all(r.external_fixture_id.endswith('correct-id') for r in rows)
    assert all(r.kickoff=='2026-09-05T14:00:00+00:00' for r in rows)


def test_sky_all_eleven_competitions_and_postponement():
    import json
    from html import escape
    from matchsignal.leagues import LEAGUES
    names = [l.name for l in LEAGUES]
    names[-2:] = ['Scottish League 1', 'Scottish League 2']
    events = [dict(id=i, competition={'name': {'full':name}}, start={'time':'19:45'},
                   teams={'home':{'name':{'full':'Home'}},'away':{'name':{'full':'Away'}}},
                   isFixture=True, isPostponed=(i==0)) for i,name in enumerate(names)]
    class Response:
        text=''.join('data-state="'+escape(json.dumps(e))+'"' for e in events)
        def raise_for_status(self):pass
    class Session:
        def get(self,*a,**k):return Response()
    provider=TheSportsDBProvider(Session())
    fixtures=provider._sky_fixtures(datetime(2026,9,29),datetime(2026,9,29,23,59))
    assert {f.competition for f in fixtures}=={l.name for l in LEAGUES}
    assert len(fixtures)==11 and fixtures[0].status=='postponed'
    assert all(f.kickoff=='2026-09-29T18:45:00+00:00' for f in fixtures)


def test_partial_daily_feed_cannot_establish_complete_coverage():
    p=TheSportsDBProvider()
    p.diagnostics=[{'source':'sky','scope':'day1','status':'success'},
                   {'source':'sky','scope':'day2','status':'failed'}]
    assert not p.covered_competitions()


def test_malformed_supported_event_degrades_only_affected_league():
    import json
    from html import escape
    event={'id':1,'competition':{'name':{'full':'Scottish Championship'}},
           'start':{'time':None},'isFixture':True}
    class Response:
        text='data-state="'+escape(json.dumps(event))+'"'
        def raise_for_status(self):pass
    class Session:
        def get(self,*a,**k):return Response()
    p=TheSportsDBProvider(Session())
    assert not p._sky_fixtures(datetime(2026,9,29),datetime(2026,9,29,23,59))
    assert 'Scottish Championship' not in p.covered_competitions()
    assert 'Premier League' in p.covered_competitions()
    assert p.diagnostics[0]['invalid_competitions']==['Scottish Championship']
