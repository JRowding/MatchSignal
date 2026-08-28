from matchsignal.ingestion import parse_csv
from matchsignal.fcstats import parse_league_page

def test_import_handles_missing_statistics():
    rows = parse_csv("Date,HomeTeam,AwayTeam,FTHG,FTAG\n01/08/2025,Alpha,Beta,2,1\n", "Premier League", "2025/2026")
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
