from matchsignal.availability import market_available

def test_sparse_statistics_disable_market():
    available, sample = market_available([{"corners": 4}] * 19, ["corners"])
    assert not available and sample == 19
