# MatchSignal 2.0

MatchSignal forecasts matches from the Premier League through the National
League. It uses Football-Data.co.uk for historic results and Football Web Pages/Sky
fixture pages (with TheSportsDB as a limited fallback) for fixtures in the next four days; neither
requires a paid account.

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

The default landing page serves `index.html`; `/performance` and `/history`
read the preserved `data/matchsignal.sqlite` ledger. Set `MATCHSIGNAL_DATABASE`
to use another database path. See [the reliability audit](PREDICTION_TRACKER_AUDIT.md)
for the architecture, known limitations, and deployment/recovery procedure.

## Refresh and backtesting

`python scripts/refresh_v2.py` imports supported Football-Data files,
imports timed fixtures from fixture providers, captures immutable prospective
predictions, and reconciles independent full-time results. Date-only unplayed
CSV rows are not eligible forecasts. It is safe to rerun against the preserved ledger.

The GitHub Action commits the SQLite ledger and static snapshot together and
retains a run artifact for recovery. This is an interim durability approach;
large deployments should use a managed datastore. Legacy predictions remain
unverified and are excluded from trusted metrics. `/health` returns 503 when
the ledger has no successful recent refresh.

## System health audit (26 September 2026)

See [SYSTEM_HEALTH_AUDIT.md](SYSTEM_HEALTH_AUDIT.md) for tested coverage and limits.
Refresh records include per-source/per-league diagnostics. Failed or incomplete
coverage blocks new freezes for affected leagues and reports degraded health.
Source warnings remain visible even when a fallback restores coverage. A recent
successful download is not proof of an upstream publisher's data completeness.

Training aliases are repaired in place; frozen forecasts and result observations
are never rewritten. Historic low-sample forecasts remain in the tracker with a
warning. The active model does not consume shot-level xG/xGA. Its `home_xg` and
`away_xg` fields are model-estimated goal means, not scraped xG statistics.
