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
    }
