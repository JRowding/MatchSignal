from matchsignal.normalization import canonical_team, team_key

def test_team_aliases_share_canonical_name():
    assert canonical_team("Man Utd") == "Manchester United"
    assert team_key("Manchester United") == team_key(canonical_team("Man United"))
