from matchsignal.ingestion import import_season, parse_csv
from matchsignal.config import CONFIG
from matchsignal.fcstats import _get, parse_league_page
import requests
import pytest

def test_import_handles_missing_statistics():
    rows = parse_csv("Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n01/08/2025,Alpha,Beta,2,1,H\n", "Premier League", "2025/2026")
    assert rows[0]["home_shots"] is None
    assert rows[0]["completed"] == 1

def test_import_ignores_invalid_date():
    assert parse_csv("Date,HomeTeam,AwayTeam\nnot-a-date,Alpha,Beta\n", "Premier League", "2025/2026") == []

def test_fcstats_completed_scores_are_parseable():
    rows = parse_league_page("""
    <tr class="matchRow darkRow"><td class="matchDate"><a href="date,2026,08,28.php">28/08/26</a></td>
    <td class="teamNameBlock_1 teamHomeName"><a href="team-a">Norwich City</a></td>
    <td class="matchResult"><a href="match">2:1</a></td>
    <td class="teamNameBlock_2 teamAwayName"><a href="team-b">Burnley</a></td></tr>
    """, "Championship", "2026/2027")
    assert rows[0]["home_team"] == "Norwich City"
    assert rows[0]["away_team"] == "Burnley"
    assert rows[0]["home_goals"] == 2
    assert rows[0]["completed"] == 1

def test_fcstats_uses_configured_timeout():
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
    _get(session, "https://example.test")
    assert session.timeout == CONFIG.source_timeout_seconds


def test_transient_source_failure_retries_and_uses_publisher_alternate(monkeypatch):
    from matchsignal.ingestion import _fetch_csv
    monkeypatch.setattr('matchsignal.ingestion.sleep', lambda seconds: None)
    calls = []
    class Session:
        def get(self, url, **kwargs):
            calls.append(url)
            response = requests.Response()
            response.status_code = 503 if '://www.' in url else 200
            return response
    assert _fetch_csv(Session(), '2526/E0.csv').status_code == 200
    assert len(calls) == CONFIG.source_retries + 2
    assert calls[-1] == 'https://football-data.co.uk/mmz4281/2526/E0.csv'


def test_source_access_errors_are_not_retried_or_hidden(monkeypatch):
    from matchsignal.ingestion import _fetch_csv
    calls = []
    class Session:
        def get(self, url, **kwargs):
            calls.append(url)
            response = requests.Response(); response.status_code = 403
            return response
    with pytest.raises(requests.HTTPError):
        _fetch_csv(Session(), '2526/E0.csv')
    assert len(calls) == 1

def test_football_data_import_uses_configured_timeout(tmp_path):
    from matchsignal.database import connect

    class Response:
        status_code = 200
        text = "Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n01/08/2025,Alpha,Beta,2,1,H\n"

        def raise_for_status(self):
            return None

    class Session:
        timeout = None

        def get(self, url, timeout, headers):
            self.timeout = timeout
            return Response()

    session = Session()
    import_season(connect(tmp_path / "test.sqlite"), 2025, session=session)
    assert session.timeout == CONFIG.source_timeout_seconds
