from datetime import datetime

from matchsignal.config import CONFIG
from matchsignal.fixtures import TheSportsDBProvider


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
