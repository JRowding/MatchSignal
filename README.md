# MatchSignal 2.0

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
