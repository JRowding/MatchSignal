# MatchSignal — fixture mismatch scanner

Find upcoming same-league fixtures where a top-30% club meets a bottom-30% club, at either venue. No predictions or betting probabilities.

Supports Premier League, Championship, League One, League Two, National League, National League North/South, Scottish Premiership, Scottish Championship and Scottish League One/Two.

## Run

```sh
pip install -r requirements.txt
python scripts/refresh_v2.py
python -m flask --app app run
```

Production entry point stays `gunicorn app:app`. `/` reads the cached snapshot, `/api/signals` returns signals and diagnostics, and `/health` returns 503 for incomplete/expired coverage. Page requests never download external data.

`SIGNAL_PERCENTAGE = 0.30` is configured centrally in `matchsignal/config.py`. Group sizes round half up: 24→7, 20→6, 12→4, 10→3. Publisher league positions are authoritative; deductions, tie-breakers and Scottish split order are not recalculated from points.

## Fixtures and display

Retains the existing Sky embedded-JSON and Football Web Pages fixture parsers, UTC storage, Europe/London display (including DST), today plus four calendar days, and day navigation. Dates and kickoff times remain visible on narrow screens. Only scheduled fixtures with known times strictly after the refresh/current time are eligible. Results are chronological; no selection cap.

Sky daily fixtures and full tables currently cover all eleven leagues. Football Web Pages remains the English fixture fallback. Sky is preferred because FWP returned 403 responses during live validation. TheSportsDB remains partial only and cannot establish complete coverage. Table failures use a labelled last-good cache, not guessed rankings. No paid subscription or API key is required.

## Refresh and deployment

The existing six-hour GitHub Action runs tests, refreshes `data/signals.json`, builds `index.html`, and commits the snapshot and `VALIDATION_REPORT.md` together. Render can continue deploying `main` using its existing configuration. Refresh exits nonzero for degraded coverage **after saving diagnostics**. A failed league does not block the others.

Snapshots expire after 12 hours. Cached data after source failure retains its original timestamps and must cover the entire requested fixture window. Client-side filtering hides kicked-off and expired fixtures between page loads. `MATCHSIGNAL_SNAPSHOT` optionally overrides the JSON path; `MATCHSIGNAL_DATABASE` is no longer used. The original SQLite ledger is retained untouched for recovery, but is neither read nor updated by this app.

## Checks and limitations

```sh
python -m pytest -q
python scripts/build_snapshot_v2.py  # rebuild HTML from cache only
```

See `REWRITE_AUDIT.md` for the baseline inspection, `VALIDATION_REPORT.md` for all eleven leagues and actual fixtures, and `REVIEW_VALIDATION.md` for independent verification and remaining acceptance gates. A successful download is not proof of absolute upstream completeness; source timestamps and parser errors remain visible. Historic audit/model documents describe the retired system.
