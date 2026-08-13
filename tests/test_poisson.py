from matchsignal.poisson import markets, score_matrix
from matchsignal.count_models import _tail

def test_score_matrix_is_probability_distribution():
    assert abs(sum(score_matrix(1.4, 0.9).values()) - 1) < 1e-10

def test_result_probabilities_sum_to_one():
    result = markets(score_matrix(1.4, 0.9))
    assert abs(result["home_win"] + result["draw"] + result["away_win"] - 1) < 1e-10

def test_no_probability_is_invalid():
    result = markets(score_matrix(1.4, 0.9))
    assert all(0 <= probability <= 1 for probability in result.values())

def test_count_tail_probability_is_valid_and_decreases_with_threshold():
    assert 0 <= _tail(9.5, 7.5) <= 1
    assert _tail(9.5, 7.5) > _tail(9.5, 9.5)
