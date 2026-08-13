from matchsignal.ingestion import parse_csv

def test_import_handles_missing_statistics():
    rows = parse_csv("Date,HomeTeam,AwayTeam,FTHG,FTAG\n01/08/2025,Alpha,Beta,2,1\n", "Premier League", "2025/2026")
    assert rows[0]["home_shots"] is None
    assert rows[0]["completed"] == 1

def test_import_ignores_invalid_date():
    assert parse_csv("Date,HomeTeam,AwayTeam\nnot-a-date,Alpha,Beta\n", "Premier League", "2025/2026") == []
