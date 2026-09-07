# MatchSignal Prediction Tracker reliability audit

Audit date: 7 September 2026. Baseline: `3dd410c` (Add prediction tracker dashboard).
This report records the pre-deployment audit. No production database was changed during that audit.
For the deployed revision and current ledger counts, inspect the live `/health` response.

## 1. Architecture

| Lifecycle stage | Implementation and audited behavior |
| --- | --- |
| Discover fixtures | `matchsignal/fixtures.py`: Football Web Pages, Sky, then TheSportsDB fallback. Explicit UK-local-to-UTC conversion for UK pages; UTC for TheSportsDB. Canonical team aliases and provider-ID aliases link matching records. |
| Gather results/model inputs | `matchsignal/ingestion.py`: Football-Data CSVs, validated full-time goals/result codes. Date-only training history is retained; timed result kickoff is preserved separately when provided. Freshly imported trusted rows are distinguished from legacy training data. |
| Calculate forecasts | `service.py` selects completed trusted history before the capture day; `predictor.py`, `features.py`, `poisson.py`, and `count_models.py` calculate features, expected goals and probabilities. Conservative same-day exclusion also protects offline backtests. |
| Freeze | `persistence.persist_prediction`: one atomic snapshot per fixture/model, current clock checked before insertion and before transaction completion. It preserves fixture context, forecast/evidence, configuration, input hash/count/cutoff and code fingerprint. Snapshot headers and probability rows are immutable through database triggers. |
| Display | `scripts/build_snapshot_v2.py` displays stored forecasts for the current model; it does not calculate forecasts. The default landing page retains its existing four market tabs. A configured dynamic scanner displays a probability-filtered subset. |
| Retrieve results | The separate append-only `result_observations` ledger receives Football-Data full-time results. Predictions are not inputs to result retrieval. FCStats is removed from the active refresh because its parser did not establish finality. |
| Grade | `settle_predictions` matches competition, canonical home/away teams and UK match date, requires one fixture identity, checks frozen/current fixture context and result kickoff where available, and waits until a later day. Ambiguous, changed, late, missing, withdrawn and unsupported cases remain ungraded. Corrections generate new settlement events. |
| Report | `reporting.py` calculates SQL aggregates for a selected model. Pick hit rates use frozen market choices; Brier/log loss and per-market calibration use all probability outcomes. Coverage and exclusion counts are visible. `/history` shows the latest 200 settled rows with model/freeze context. |
| Schedule/store | GitHub Actions runs every six hours, serializes jobs, checks out current `main`, runs the suite, refreshes, backs up the ledger as an artifact, and commits SQLite plus the static page together. Flask reads the bundled ledger by default, or an explicit `MATCHSIGNAL_DATABASE`. |

The four old head-to-head scripts use a separate database and are not in the active workflow. Their destructive regeneration and retrospective calculations are unsuitable for this tracker. Offline `backtesting.py` remains separate from prospective performance statistics.

## 2. Critical findings

The original implementation was **NOT TRUSTWORTHY YET**.

1. **History was destroyed every refresh.** The workflow deleted `data`, committed only HTML, and never preserved the SQLite ledger. Render's local filesystem was not a durable substitute.
2. **Fixture IDs could belong to the wrong match.** The FWP regex crossed HTML row boundaries. Live reproduction attached a Birmingham/Wolves URL to Blackburn/Sheffield United; another mismatch affected Bromley/Wimbledon. Missing fields were borrowed from later rows.
3. **Freezing could occur after kickoff.** Only the generation loop checked kickoff; direct persistence accepted historical fixtures. The original tests actually saved already-played fixtures and considered that success. There was no transactional clock-boundary protection or database immutability.
4. **Results normally could not match.** The importer stored dates; timed fixture strings were compared for exact equality. Team aliases were also incomplete, including Man City, Newcastle and Tottenham.
5. **Accuracy was mathematically misleading.** Every home/draw/away event was counted as a pick. Exactly one occurs per fixture, yielding 33.3% across those rows regardless of which outcome was favored. Both BTTS/winner directions were also pooled. Models were mixed; calibration omitted probabilities below 50%.
6. **Result correction/finality was unsafe.** Only unsettled rows were processed, so corrected scores never changed prior grades. A scraped score alone was treated as a completed match. Postponements and identifier changes had no safe reconciliation policy.
7. **The live model could fail or use the wrong evidence.** Aware kickoff timestamps reached naive feature dates. Away count-form admitted unrelated away teams. Zero-goal samples could divide by zero. Same-day date-only history was insufficiently separated in retrospective evaluation.
8. **Legacy context could be fabricated by migration.** Missing frozen fields were filled from mutable fixture records. Older schemas could fail on indexes referencing columns before those columns were migrated.

## 3. Improvements made

- Added immutable snapshot headers, prediction-field/delete protections, probability-to-snapshot consistency checks, unique snapshot/market records, atomic writes, input validation, and duplicate/top-up prevention.
- Retained original legacy rows without certifying them. Legacy predictions and unverified training rows are excluded from the trusted pipeline; no historical probabilities were recalculated or invented.
- Bounded FWP parsing to individual rows, rejected unknown kickoff times, normalized timezones and expanded deterministic team aliases. Same-day provider IDs map to one fixture; conflicting identities require review.
- Added an independent result ledger and append-only settlement history. Corrected and explicitly withdrawn results are reconciled; ambiguous records are not guessed. Date-only results can grade forecasts frozen before that match day; same-day snapshots require result kickoff evidence.
- Preserved model version from the actual forecast, configuration, forecast/evidence JSON and code/input fingerprints. Incremented the model to **2.5.1** for the evidence/cutoff/count-form changes.
- Replaced pooled outcome "accuracy" with defined pick hit rates; added model selection, home/away/draw breakdowns, complete probability-range calibration, independent fixture counts and missing/review/legacy counts. Aggregation stays in SQL.
- Preserved the ledger in the scheduled workflow and added run artifacts, serialization, latest-main checkout and the full test gate. Added refresh-run records and a health response that reports missing, stale or failed tracker refreshes instead of unconditional success.
- Closed Flask database connections, escaped source text in dynamic HTML, kept version/context visible in history/detail views, and added Tracker/History navigation to newly generated static pages.

## 4. Testing

- Baseline: **28 tests passed**, demonstrating that the existing tests did not establish trustworthiness.
- Final expanded suite: **62 tests passed in 121.88 seconds** on local Python 3.14. The workflow runs Python 3.12; its hosted run has not been executed here.
- Regression coverage includes all seven enabled market truth tables (draws, clean sheets, BTTS and combined winners), invalid scores/probabilities, post-kickoff/unknown-time rejection, clock-boundary rollback, injected mid-batch failure, competing writers, duplicate IDs, fixture ambiguity, postponement/abandonment/cancellation, reschedules, corrections, withdrawals, missing results, legacy migration, restart idempotency, model-separated reporting, same-day leakage, away-form filtering, UK summer/winter time, persistent identity-conflict flags and SQLite replacement-write protection.
- Flask test-client requests exercised landing, tracker, history and fixture detail routes; missing refresh history returns health status 503. Python application files compile; whitespace validation passes.
- Live Football-Data check: **380/380 completed matches** parsed from the 2025/26 Premier League CSV. Its field definitions identify FTHG/FTAG as full-time goals and FTR as full-time result. [Source definitions](https://www.football-data.co.uk/notes.txt).
- Live fixture check: **13 upcoming fixtures** were returned. The faulty cross-row IDs were reproduced before the fix and matched their own row's teams after it. No fixtures were returned for Premier League or League Two in that window; absence is not proof of complete coverage.
- Synthetic scale check: **100,002 predictions / 14,286 fixtures**. Settlement **4.513 s**; idempotent rerun **1.966 s**, **zero changes**; report **0.743 s**; SQLite integrity check **ok**. This was in-memory synthetic data and excludes filesystem, network, deployment and sustained-load costs.

## 5. Remaining risks

- **Deployment is unproven.** There was no local historical database to inspect and no production access/configuration supplied. The scheduled Git push, artifact restore and deployed health behavior need an actual run. Lost original database history cannot be certified by this migration.
- **Source completeness remains unknown.** A successful refresh can have partial source failures; warnings and missing-result counts help but there is no authoritative expected-fixture denominator or per-league freshness alarm. Disappearing fixtures and source rows deleted entirely are not automatically reconciled. Explicit score withdrawal is supported; silent deletion is not.
- **Identity/status reconciliation is conservative, not complete.** Names are aliases rather than a full stable team registry. Reschedules with changed IDs, unknown kickoff times and conflicting providers may require manual review. The fixture feeds are scraped or limited; TheSportsDB documents free-tier rate limits and incomplete methods. [Provider documentation](https://www.thesportsdb.com/documentation).
- **Durability at scale needs a different store.** Git-tracked binary SQLite and 90-day artifacts are an interim recovery mechanism. Git history grows; push failures need artifact recovery. Settlement still revisits all verified rows for corrections and holds a write transaction; larger persistent workloads need measured incremental processing.
- **Reproducibility has limits.** Frozen outputs/features/configuration are retained, but only a hash of the full input dataset is stored. Re-running the exact forecast later requires independently retained raw inputs and source code. Offline backtests can include later source corrections and must not be represented as prospective performance.
- **Statistics remain conditional.** Four correlated market picks per fixture are not four independent matches. Unobserved/missing matches can bias results. There are no confidence intervals, baseline comparisons, full coverage analysis, or separately frozen scanner top-20 selections. "HIGH" confidence is a sample-count label, not demonstrated calibration.
- **This is application-level integrity, not tamper-proof attestation.** A database owner can remove triggers, replace files or change clocks. Independent timestamped publication/signing is needed for an adversarial audit trail.

## 6. Recommended next improvements

| Priority | Next action |
| --- | --- |
| Critical | Deploy and observe a complete freeze → finish → independent result → grade cycle. Restore an artifact in a staging copy and confirm the same IDs/probabilities/grades. Preserve any surviving historical database before migration; never relabel legacy rows as verified without independent evidence. |
| High | Use durable managed storage and backups; replace scraped identity/status reconciliation with stable provider fixture/team IDs. Add per-league freshness, expected coverage, failure alerts and a reconciliation queue. Detect result deletion and track old unresolved seasons beyond the rolling import window. |
| Medium | Archive input datasets/source responses by content hash; add incremental settlement/correction scans, pagination and indexes measured against on-disk workloads. Add confidence intervals, league/base-rate and bookmaker baselines, multi-class winner Brier/log loss, and lead-time/cohort comparisons. |
| Nice-to-have | Reliability plots, version comparison views, frozen scanner-selection cohorts, read-only exports, and externally timestamped/signed snapshot manifests. |

## 7. Verdict

**FUNCTIONAL BUT NEEDS IMPROVEMENT** for the patched local implementation.

The reproduced integrity failures are addressed and covered by tests. It is not yet **RELIABLE** as an operated service because durable deployment/recovery has not been demonstrated and feed completeness/status reconciliation still require supervision. It is not **PRODUCTION-GRADE** at large scale without managed durability, monitoring, reconciliation and operational load validation. The currently deployed version, if unchanged from the audit baseline, remains **NOT TRUSTWORTHY YET**.

## Deployment and recovery checklist

1. Preserve a copy of any surviving ledger, including its Git/source context. Run migration against a copy first. The audit intentionally leaves legacy predictions unverified.
2. Install the updated requirements (including `tzdata`), run the suite, then run `scripts/refresh_v2.py` and `scripts/build_snapshot_v2.py` using the intended database path. The default path is `data/matchsignal.sqlite`.
3. Confirm the workflow commits **both** SQLite and HTML and that Render deploys that commit. Existing committed `index.html` was not regenerated with synthetic audit data.
4. Confirm `/performance` shows the new model and coverage counts and `/health` returns 200 after a successful recent refresh. If the hosting platform uses `/health` as deployment liveness, account for its new 503 behavior until the tracker has successfully refreshed.
5. On a failed push, use the run's `prediction-ledger-<run_id>` artifact. Restore to a separate database path, run `PRAGMA integrity_check`, compare snapshot counts/hashes against the last committed ledger, and reconcile before replacing anything. Never silently restart from an empty file.
6. After downtime, rerun against the preserved ledger. Existing snapshot batches remain unchanged; missed pre-match snapshots are not backfilled. Review missing/changed/ambiguous rows explicitly.
