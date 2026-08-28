from dataclasses import dataclass

MODEL_VERSION = "2.4.0"
SUPPORTED_COMPETITIONS = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One",
    "E3": "League Two", "EC": "National League",
}

# Shared rating priors make promotions, relegations and cup ties comparable
# before the teams have accumulated matches in their new division.
COMPETITION_ELO_PRIORS = {
    "Premier League": 1650.0, "Championship": 1550.0,
    "League One": 1475.0, "League Two": 1410.0, "National League": 1350.0,
}

@dataclass(frozen=True)
class ModelConfig:
    recent_window: int = 10
    form_window: int = 5
    min_sample: int = 5
    poisson_max_goals: int = 8
    home_advantage: float = 1.08
    elo_k: float = 20.0
    scanner_min_probability: float = 0.58
    scanner_max_probability: float = 0.94
    fixture_lookahead_days: int = 4
    enabled_markets: tuple[str, ...] = ("home_win", "draw", "away_win", "over_2.5")

CONFIG = ModelConfig()
