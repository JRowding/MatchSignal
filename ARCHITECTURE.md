# MatchSignal scanner architecture

1. `leagues.py` defines the eleven competitions and publisher identifiers.
2. `fixtures.py` retains the existing Sky/FWP parsers and extends league mappings. Sources use bounded timeout/retry handling. Sky daily pages are the primary source after observed FWP failures; FWP and partial SportsDB remain fallback integrations.
3. `standings.py` reads full publisher-ranked Sky tables, rejects wrong pages, malformed ranks, small/duplicate tables and ambiguous identities.
4. `normalization.py` retains and extends explicit aliases; `mismatch.py` uses deterministic keys within the same competition, never fuzzy matching.
5. `mismatch.py` computes symmetric top/bottom groups and selects qualifying scheduled fixtures in chronological order. Unknown clubs and contradictory fixture times are withheld and reported.
6. `refresh.py` isolates table failures per league, retains bounded last-good caches and atomically writes JSON. It records source outcomes, counts, unmatched teams, warnings and original refresh timestamps.
7. `dashboard.py` and `templates/dashboard.html` retain UK kickoff formatting, day navigation and the dark/lime visual identity. Flask renders from the snapshot without network calls. The scheduled command also produces static HTML and the all-league report.

The old prediction, statistics import and grading modules, routes and tests are removed. Their history remains in Git, and the original SQLite ledger is unchanged. There is no migration of old forecasts into MatchSignals.

Deployment remains Flask/Gunicorn plus scheduled GitHub Actions and repository-backed snapshots, compatible with Render's ephemeral filesystem. No external database or new service is required.
