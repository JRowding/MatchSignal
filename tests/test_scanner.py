from matchsignal.scanner import strongest

def test_scanner_orders_and_filters_probabilities():
    signals = strongest([{"probability": .65}, {"probability": .95}, {"probability": .72}])
    assert [signal["probability"] for signal in signals] == [.72, .65]
