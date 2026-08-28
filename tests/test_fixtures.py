from datetime import datetime

from matchsignal.fixtures import TheSportsDBProvider


def test_football_web_pages_time_parser_handles_common_kickoff_times():
    assert TheSportsDBProvider._football_web_pages_kickoff("28/8/2026", "7.45pm") == datetime(2026, 8, 28, 19, 45)
    assert TheSportsDBProvider._football_web_pages_kickoff("31/8/2026", "3pm") == datetime(2026, 8, 31, 15, 0)
