# MatchSignal full system audit — 26 September 2026

Baseline/deployed revision inspected: `fc9b4d39f90b09254825ed5a503375814a3bd32f`.
Application: https://matchsignal.onrender.com. Model: 2.5.1. Python tests: 3.12.
This report distinguishes observed production defects from verified fixes on an isolated copy. Deployment verification is recorded at the end.

## MATCHSIGNAL HEALTH SCORECARD

Statuses below describe the tested repaired implementation, not an assertion that all external data is complete.

| Component | Status | Evidence / limit |
|---|---|---|
| Fixtures | 🟡 WORKING BUT NEEDS ATTENTION | Repaired Sky parser matches 38 scheduled fixtures; six explicit postponements. Scraped schedules are not an authoritative completeness guarantee. |
| Data sources | 🟡 WORKING BUT NEEDS ATTENTION | All 20 Football-Data season files retrieved; Sky fallback works. FWP returned timeouts/403s here; SportsDB season responses returned only five events. |
| Team statistics | 🟡 WORKING BUT NEEDS ATTENTION | Aliases repaired; 420 current-season rows checked against source across all five leagues. Historical frozen input defects remain disclosed. |
| Prediction engine | 🟢 WORKING | 1,246 independent market calculations agree to <=5.6e-16; methodology retained. This is mathematical correctness, not demonstrated forecasting skill. |
| Prediction freezing | 🟢 WORKING | 178 snapshot hashes intact, all captured before kickoff; correction/restart/concurrent-writer/rollback tests pass. |
| Results | 🟡 WORKING BUT NEEDS ATTENTION | Recovered all 21 previously unmatched results in ledger copy; dependent on one trusted final-score publisher. |
| Auto-grading | 🟢 WORKING | 147 recovered market grades, 980 total; rerun made zero changes. All 833 original grades agree with independent truth tables. |
| Reliability tracker | 🟡 WORKING BUT NEEDS ATTENTION | Arithmetic checked; market buckets separated; 24 of 38 calibration groups have fewer than 30 outcomes. Input defects and selection/coverage bias prevent a blanket accuracy claim. |
| League coverage | 🟡 WORKING BUT NEEDS ATTENTION | Five supported English leagues tested individually; no other leagues enabled in current code. |
| Mobile frontend | ⚪ NOT TESTABLE | Mobile CSS and kickoff visibility repaired and unit-checked, but no mobile/Safari rendering verification. Browser URL policy blocked local preview; no supported viewport-emulation control was exposed. |
| Desktop frontend | 🟡 WORKING BUT NEEDS ATTENTION | Live original tabs, day filters and tracker navigation tested; new HTML/routes tested locally. Repaired browser rendering requires deployment verification. |
| Performance | 🟢 WORKING | Five real model calls ~1.14 s total; local tracker ~6.7 ms; real full refresh ~62.4 s. These are observed workload measurements, not load-test guarantees. |
| Error handling | 🟡 WORKING BUT NEEDS ATTENTION | Failed/invalid/partial sources recorded; affected new freezes withheld; tests cover missing data, corrupt structures and failure persistence. Silent upstream omissions still possible. |
| Data freshness | 🟡 WORKING BUT NEEDS ATTENTION | Fresh/stale/failed/degraded state, source warnings and last successful refresh now separate. Cannot infer upstream correctness from HTTP success. |

## Verified pipeline and scope

1. GitHub Actions runs `scripts/refresh_v2.py` every six hours (execution can be delayed), with one serialized ledger writer.
2. `ingestion.py` downloads four seasons for E0/E1/E2/E3/EC, parses full-time scores/statistics, validates identities, canonicalizes team names, and stores mutable training matches plus append-only independent result observations.
3. `fixtures.py` reads FWP monthly HTML, Sky daily embedded event JSON, and a limited SportsDB season fallback. UK-local times are stored as UTC. Explicit Sky postponed/cancelled/abandoned/completed states now propagate.
4. `service.py` selects trusted completed history strictly before the capture day. Unknown teams and incomplete league source refreshes now block new freezes.
5. `features.py` computes separate recency-weighted home/away/all-venue form from at most ten matches; chronological Elo across the English pyramid; results-derived current-season league table.
6. `predictor.py` combines goal rates, home advantage, bounded Elo/table adjustments and fallback venue samples. `poisson.py` normalizes a 0–8 score grid. Count markets are separately calculated when samples support them, but only seven configured goal/result markets are persisted/graded.
7. `persistence.py` freezes one immutable snapshot per fixture/model at first discovery, often days before kickoff. Snapshot includes input metadata, forecast/evidence/configuration and code hash. It does not continually update until kickoff.
8. `build_snapshot_v2.py` displays frozen probabilities in the existing four-tab dashboard. Flask serves it and database-backed health, tracker, history and fixture-detail routes.
9. Next-day settlement matches competition, canonical teams and match date to independently imported final scores; changed/ambiguous/late/nonfinal cases are excluded. Corrections append settlement events.
10. Reporting aggregates by model and individual market; SQLite and HTML are committed together and an artifact backs up the ledger.

No external n8n job is referenced by the active repository workflow. The four legacy head-to-head scripts and FCStats importer are inactive; they were inspected but not executed against the live ledger. README's previous single-fixture-source description was stale. No active FBref xG/xGA feed exists: `home_xg`/`away_xg` are estimated Poisson goal means. Most-likely score and league-selector UI are not features of the current four-tab dashboard; neither was invented for this audit.

## PROBLEMS FOUND

| Severity | What was wrong / why | Targeted change and validation |
|---|---|---|
| High | Missing aliases such as Accrington/Accrington Stanley, Oldham/Oldham Athletic, Boston Utd/Boston United, Carlisle/Carlisle United, Solihull/Solihull Moors, Aldershot/Aldershot Town, Scunthorpe/Scunthorpe United, Yeovil/Yeovil Town and Fylde/AFC Fylde split training and fixture identities. | Expanded exact aliases, including observed Sky Newport County AFC and FC Halifax names. Repair mutable training names in place; abort on uniqueness conflicts. 8,184 training rows preserved. All 21 missing results recovered. |
| High | Unknown fixture teams silently received league-baseline goals. 35 of 178 frozen fixtures had zero usable history for at least one side: six League Two and 29 National League. Four forecasts had identical H/D/A vectors. | Block future freezes for missing team history, log missing names, flag old low-sample forecasts. Preserve all 178 original payloads and all original probabilities. Historical bad forecasts are not retroactively improved or deleted. |
| High | Sky renamed its competition labels to EFL Championship/League One/League Two. The parser silently discarded them; National League was absent from its map. | Accept current and existing names; add National League mapping. Replayed actual downloaded Sky pages and recovered all 38 scheduled fixtures. |
| High | Feed parsers skipped nonfixture events, so explicit postponements could fail to update existing records. Successfully settled fixtures remained `scheduled`. | Carry explicit Sky lifecycle states; terminal states take precedence in deduplication; reconcile completed/withdrawn fixtures. Six postponements recognized; unit tests prove status propagation and no invalid grading. FWP-only disappearance remains a risk. |
| High | Any nonzero history import marked the whole refresh successful, even if a league or fixture source failed. Empty HTML/CSV could look like zero football activity. | Validate CSV schema/completed rows; track per-source/league outcomes; distinguish invalid/partial responses; require a usable statistics and fixture refresh before new freezes. Preserve old snapshots and expose degradation rather than inventing zeros. |
| High | Failed refreshes could stop CI before the failure record reached deployment. Missing bundled storage could create an empty ledger. | Preserve and publish diagnostic ledger/snapshot after refresh failure, then fail the workflow gate. Require an existing ledger in scheduled operation. Crash/failure/degraded records tested across reopen. Hosted failure-path recovery remains unexercised. |
| Medium | No landing-page freshness information; health merged stale and failed states. | Shared refresh state with last success, last attempt, source warnings and per-league counts; static warning ages in browser even without later regeneration. |
| Medium | Clicking a fixture row also triggered the day filter because listeners selected every `data-day` element. Empty tables were not fully hidden. Mobile CSS hid kickoff time entirely. Static pages could retain started fixtures until another refresh. | Limit filter listeners to buttons, fix hidden-table CSS, show time within mobile fixture text, remove started fixtures at build time and in the browser every minute. UK-calendar filtering aligned with displayed times. |
| Medium | A probability-range summary pooled different market groups. Small samples were only warned about generically. | Separate market-group/range summary and mark individual calibration samples under 30; retain clearly labelled overall-picks summary. Add historical input-quality counts. |
| Medium | Negative optional statistics could enter count models; nonfinite/unrepresentable Poisson means failed unclearly. | Negative optional counts remain missing, not zero; explicit probability-input validation. Relevant boundary tests pass. |
| Low | Flask requests repeatedly ran schema migrations; separate HTTP requests did not share a session; fallback queried SportsDB even after Sky verified an empty league window. | Open serving connections read-only, reuse refresh HTTP session, skip redundant fallback after checked coverage. Preserve simple architecture and full correction scan. |
| Low | January–June season loop requested a not-yet-started season. | Use July-based football-season boundary. No change to rolling four-season model horizon. |

## FIXES MADE

Meaningful changes: `normalization.py` (aliases); `ingestion.py` (training repair, source validation/diagnostics); `fixtures.py` (Sky labels/statuses, bounded retries, diagnostic coverage, fallback rules); `service.py` (missing-team/source gates); `persistence.py` (fixture lifecycle); `poisson.py` (input validation); new `health.py`; `reporting.py` (market buckets/sample/input warnings); `app.py` (read-only serving, health, scrollable tables); `refresh_v2.py` (season boundary, session, per-league health and preserved failure state); `build_snapshot_v2.py` (freshness/time/filter fixes); workflow durability/failure reporting; README; `test_system_audit.py` regression coverage.

No dependency added. Prediction formula, model version, enabled markets, working leagues and frozen historical data remain unchanged. A changed code fingerprint records future implementation changes without mislabelling the model methodology.

## TESTS PERFORMED

- Baseline suite: 66 passed. Repaired suite: 101 passed (~0.35 s), including existing concurrency, rollback, immutability, source/timezone, market truth-table, correction, abandonment and legacy tests. Python compilation and whitespace checks passed.
- Read production `/health`: HTTP 200, exact baseline revision, 178 fixtures, 1,246 verified probability rows, 833 settled rows. Last five hosted refresh runs reported success before the audit, demonstrating why CI success alone was insufficient.
- SQLite integrity `ok`; no foreign-key violations. Verified every snapshot SHA-256 against payload and every recorded freeze precedes kickoff.
- Independent Poisson recurrence calculated seven markets across all 178 frozen fixtures (1,246 comparisons), maximum discrepancy 5.55e-16. All probabilities finite/in range and H+D+A sum to one. Maximum omitted score-grid mass before normalization was 0.3642%; truncation retained as existing methodology.
- Independent outcome truth tables checked all 833 original settled rows without a mismatch.
- Downloaded and compared 420 current-season source rows against stored goal/shot/SOT/corner/foul values: Premier League 50, Championship 95, League One 83, League Two 84, National League 108; zero numeric mismatches after identity resolution.
- Independently checked raw-CSV home weighting and samples for Fulham, Norwich City, Wigan Athletic, Salford City and Hornchurch. Example weighted home GF/GA: 1.630/2.260, 2.548/2.067, 0.735/1.977, 1.018/0.469, 1.159/0.259 respectively. These current-season spot checks do not imply the production model uses only current-season form.
- Ledger-copy migration/import/settlement: 147 new grades across 21 missed fixtures, total settled 980; rerun zero; 178 payloads byte-for-byte unchanged; training row count unchanged.
- Independent Python aggregation agrees with SQL counts, successes and average probabilities for 38 model/market/bucket groups; 24 have fewer than 30 outcomes.
- Real model calls with repaired inputs in all five leagues: ~0.22–0.25 s each, sample 10. Full real refresh on copied ledger: 8,184 imported rows, 44 fixture/status records, ~62.4 s; fallback restored all five league schedule checks despite primary failures.
- Flask test client: landing, health, performance, history and valid detail HTTP 200; missing detail 404. Local responses roughly 1–7 ms. This excludes network/Render cold-start/load.
- Live browser: all market tabs, day selection, empty-day state and tracker navigation exercised. Desktop page did not overflow its viewport. Captured errors were extension-origin, not evidence of application JS errors. Local and data-URL browser previews were policy-blocked; no Safari/mobile rendering pass is claimed.

### League test matrix (26–30 September window)

| League | Source training rows (four seasons) | Scheduled fixtures | Explicit postponements | Baseline settled fixtures → repaired | Model / mapping |
|---|---:|---:|---:|---:|---|
| Premier League | 1,190 | 0 | 0 | 20 → 20 | Real model call works; timed freeze test synthetic because none upcoming |
| Championship | 1,751 | 0 | 0 | 35 → 35 | Real model call works; timed freeze test synthetic because none upcoming |
| League One | 1,739 | 4 | 4 | 25 → 25 | All upcoming teams map |
| League Two | 1,740 | 10 | 2 | 20 → 24 | Aliases repaired; original six zero-sample forecasts retained |
| National League | 1,764 | 24 | 0 | 19 → 36 | Aliases repaired; original 29 zero-sample forecasts retained |

Every scheduled fixture in the retrieved Sky window matched the baseline's date, time, home and away identity after canonicalization: no additional missing or duplicate scheduled fixture was found. Premier League/Championship empty windows are consistent with the international break, not treated as proof of a feed failure. The EFL's current schedule/broadcast publication was checked as an additional reference; actual per-fixture comparisons used downloaded Sky event records. National League completeness lacks an independently accessible primary schedule in this environment.

## REMAINING RISKS

- Scraper structure, names, rate limits and provider availability can change. Successful parsing cannot detect every silent omission. FWP was inaccessible here; the tests prove recovery through Sky, not FWP live parser correctness. SportsDB's truncated season response is not a dependable completeness fallback.
- Sudden disappearance, date changes with new IDs, and FWP-only postponements still need reconciliation. Terminal Sky flags are handled; unknown-time fixtures remain unforecast. Six-hour scheduling can miss late additions or freeze forecasts well before kickoff.
- Historical forecasts with missing input teams remain real, flawed forecasts. They are flagged, never retrospectively repaired. Reliability after recovering their results may change; that is correction of missing outcomes, not improving historical predictions.
- All five result collectors depend on Football-Data finality/corrections. Source rows silently removed entirely are not equivalent to explicit withdrawals. Prior seasons outside the rolling window stop receiving corrections.
- Official table sanctions/points deductions are not in the results-derived table. Expected goals are not shot-level xG. Low sample counts, promotion, team changes and correlated markets limit interpretation. No claim of profitable picks or out-of-sample predictive advantage was established.
- SQLite committed to Git plus 90-day artifacts remains interim durability. Push/deployment failure, workflow suspension, repository growth and Render deployment lag require operational monitoring. A complete hosted backup restoration, severe-load test and hosted crash-recovery drill were not performed.
- Cached upstream content may be old despite HTTP success. Health now exposes source outcomes/latest result dates; it does not independently know every expected match/result.
- Mobile/iPhone Safari and repaired browser rendering are not fully verified here. The browser's security policy blocked local test URLs; no bypass was attempted after that explicit policy rejection.

## MATCHSIGNAL CURRENT STATUS

The repaired pipeline has been exercised against live inputs and an isolated copy of real historical data:
Fixtures → Statistics → Predictions → Frozen Predictions → Results → Grading → Reliability.
Existing predictions remain immutable; all previously unmatched historical results were recovered in testing. Mathematics and grading are correct for the tested evidence. Input quality, source completeness and historical zero-sample forecasts prevent declaring all outputs trustworthy without qualification.

### Deployment verification

Not deployed. Automatic approval review rejected a direct push to `main` because the audit request did not explicitly authorize changing the shared live branch. The tested changes are provided on `audit/system-health-2026-09-26` for review and approval. No production database or historical forecast was changed by this audit. The baseline live application still has the mapping/fallback/freshness defects described above; its 833 settled forecasts must not be confused with the 980 achieved on the repaired test copy.

After an approved merge, the normal hosted refresh must run against its preserved ledger, then `/health`, the deployed revision, 178 existing snapshot payloads and repaired settlement counts must be checked. New fixtures may increase totals after this audit. Hosted refresh/deployment verification is outstanding, and approval to merge/publish is required by the automatic review decision.
