from dataclasses import dataclass

SIGNAL_PERCENTAGE = 0.30
CACHE_MAX_AGE_HOURS = 12

@dataclass(frozen=True)
class FixtureConfig:
    fixture_lookahead_days: int = 4
    source_timeout_seconds: int = 15
    source_retries: int = 1

CONFIG = FixtureConfig()
