# Mismatch scanner: baseline inspection

Baseline: 778459c. Existing Flask `/` and `/health` returned 200. All 101 existing tests passed before changes (27 September 2026).

## Reuse

`matchsignal/fixtures.py`: Fixture dataclass, per-row Football Web Pages parsing, Sky embedded JSON event parsing, status filtering, bounded network calls, and deterministic team aliases. Dates from these publishers are Europe/London local time, converted explicitly to UTC by `timeutils.py`. Preserve today plus the next four calendar days (including midweek), then omit fixtures already started. Existing snapshot day navigation and 12-hour UK kickoff presentation are retained; full dates are added explicitly and results ordered chronologically rather than by prediction probability.

Existing sources cover five English leagues. FWP is primary, Sky supplements all dated pages, TheSportsDB is a partial last resort. Live baseline probe: Sky accessible; FWP HTTP 403 in this environment. A partial SportsDB response cannot establish complete coverage.

## Replace

Poisson, Elo, goal/count markets, prediction freezing, grading, history/performance routes and historical CSV refresh are no longer part of the active application. Git history preserves their implementation; the original SQLite ledger is left untouched for recovery. No prediction ledger migration is needed for the scanner.

## Deployment and cache

Flask/Gunicorn entry point remains `app:app`. Existing GitHub Actions refresh every six hours and commit a generated dashboard for Render's ephemeral filesystem. Retain that mechanism, replacing the output with an atomic JSON scanner snapshot plus HTML and a validation report. Requests never fetch external feeds. Preserve last-good data per league with explicit degraded status and expiry, rather than reporting stale data as freshly checked.

Repository has no Render YAML or local `.env`; live Render environment settings are not available here. Previous `MATCHSIGNAL_DATABASE` is obsolete for the scanner. New optional `MATCHSIGNAL_SNAPSHOT` selects the JSON snapshot path. No new keys or paid services required.

## Additional checks

Validate tables using publisher positions, unique normalised identities and a complete contiguous rank sequence. Never recalculate order from points (deductions and Scottish split ordering must be preserved). Classify only same-league fixtures, reject unknown names/conflicting kickoffs, record incomplete evaluations. No fuzzy matching.

## Demonstrated source adjustment

The first eleven-league refresh succeeded through Sky while fourteen FWP monthly requests failed (403/timeouts). Therefore the existing Sky integration now runs first and FWP is requested only for uncovered leagues. A second live refresh exposed intermittent five-second read timeouts, so the bounded timeout was increased to fifteen seconds, retaining one retry. This changes source ordering and tolerance, not date parsing or presentation.
