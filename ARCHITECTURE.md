# MatchSignal 2.0 architecture and phased rebuild

## Audit of the original repository

The original application was a Flask wrapper that served a pre-rendered HTML
file. It used four standalone scripts to download Football-Data CSV files,
scrape a public livescore page, and calculate a direct head-to-head percentage.
It had a single SQLite file generated during a GitHub Action. There were no
routes beyond the landing page, no stable schema for fixtures/predictions, no
team registry, no historical prediction records, tests, or leakage protection.

The compact visual style and Render deployment can be retained. The original
data parsing and head-to-head model cannot be the forecasting core because they
mix data concerns and do not preserve pre-match predictions.

## Phases

1. Foundation: canonical teams, configurable English leagues, database schema,
   chronological features, Poisson probability model, tests. **In progress.**
2. Robust Football-Data importer for five English competitions and fixture
   provider abstraction.
3. Persisted fixture prediction generation and signal scanner.
4. Dashboard, match detail, history and performance routes.
5. Chronological backtesting and calibration reporting.
6. Corners and cards only where data quality supports them.

## Deployment constraint

Render's free filesystem is ephemeral, so persistent prediction history cannot
live only inside the service. The no-cost deployment approach is a scheduled
GitHub Action that imports data, regenerates a static prediction snapshot, and
commits it. A future database-backed deployment needs a durable datastore.
