from dataclasses import dataclass

MODEL_VERSION = "2.0.0"
SUPPORTED_COMPETITIONS = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One",
    "E3": "League Two", "EC": "National League",
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

CONFIG = ModelConfig()
