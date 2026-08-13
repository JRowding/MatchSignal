from matchsignal.metrics import brier_score, calibration, log_loss

def test_metrics_for_perfect_predictions():
    pairs = [(1.0, 1), (0.0, 0)]
    assert brier_score(pairs) == 0
    assert log_loss(pairs) < 1e-9

def test_calibration_has_samples():
    assert calibration([(.7, 1), (.72, 0)])[0]["count"] == 2
