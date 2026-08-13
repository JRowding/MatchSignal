from matchsignal.poisson import markets, score_matrix

def test_score_matrix_is_probability_distribution():
    assert abs(sum(score_matrix(1.4, 0.9).values()) - 1) < 1e-10

def test_result_probabilities_sum_to_one():
    result = markets(score_matrix(1.4, 0.9))
    assert abs(result["home_win"] + result["draw"] + result["away_win"] - 1) < 1e-10

def test_no_probability_is_invalid():
    result = markets(score_matrix(1.4, 0.9))
    assert all(0 <= probability <= 1 for probability in result.values())
