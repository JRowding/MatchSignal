# MatchSignal 2.0

MatchSignal forecasts matches from the Premier League through the National
League. It uses Football-Data.co.uk for historic results and TheSportsDB's
public fixture feed for the upcoming round; neither requires a paid account.

The model carries one Elo rating across the five tiers, with conservative
division priors. That means promotions, relegations and cross-division/cup
fixtures can be assessed rather than silently excluded.

An English-football probability scanner. It is being rebuilt from a direct
head-to-head dashboard into a measurable forecasting system.

## Supported competitions

Premier League, Championship, League One, League Two and National League.

## Model foundation

The first model uses chronological home/away form, recency weighting, Elo and
a Poisson score model to derive result, goals, BTTS, team goals and
double-chance probabilities. See [MODEL.md](MODEL.md).

## Development

```text
pip install -r requirements.txt
pytest
```

The current Render app continues to serve `index.html` while the data pipeline
and dynamic dashboard are built. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Refresh and backtesting

`python scripts/refresh_v2.py` imports supported Football-Data files,
creates scheduled fixtures from unplayed source rows, generates immutable
predictions, and settles completed records. It is safe to rerun.

The free GitHub Action refreshes a static snapshot. For complete long-term
prediction history and a dynamic fixture provider, deploy the same database to
a durable datastore.
