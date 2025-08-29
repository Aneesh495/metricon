# Build status

## Current verification

The select correction passed all 12 local acceptance gates and independent verification. The next hosted campaign stopped at a numerical test: Linux's independent scalar/NumPy logarithms differed by one representable rounding step. The test now allows two rounding steps and additionally checks exact observation counts and the next unit's changed performance estimate. Coupled-answer feature equality remains exact. The recorded local campaign below is historical while this test correction receives fresh acceptance and hosted Linux verification. Next action: complete those checks and refresh the measured reports.

The frozen source passed the complete correctness campaign and independent verification on October 2, 2026. All 12 required correctness gates passed, together with 100 Python tests, 10 client unit tests and 66 browser cases. Synthetic predictive targets passed. Canonical import throughput remains below its tuning objective and is reported separately.

A clean source checkout installs before client compilation. Distribution wheels contain the compiled workbench, recovery manifest and exact dependency lock; an installed wheel was checked from outside the checkout. Dataset versions and temporal folds remain pinned across task submission, diagnostics, comparison and replay. Committed research payloads are checksum-checked before display. Deep links preserve workspace/version/learner/run context, and data changes clear prepared exports.

Browser verification covers laptop Chromium, touch Chromium and mobile WebKit. Every section is checked at 320, 360, 390, 768, 1280 and 1440 pixels, alongside actual fitting, rejection inspection, calibration, model comparison, running cancellation, exports and keyboard navigation. These are browser emulations, not physical-device measurements. Real network/module failures expose recovery controls. Simulation cancellation is cooperative, progress counts completed trials, and unaffordable budgets or repeated policy names are rejected before queuing work.

The [review](reports/REVIEW.md) records each reproduced defect and its regression. Failed traces, interrupted campaigns and raw negative results remain retained locally. Only the final source-matched campaign is accepted. The complete laboratory uses its local Python service; GitHub Pages cannot execute that service.

## Implemented contracts

| Modules | Implemented behavior and source |
| --- | --- |
| Schema, ingestion and quality | [Strict canonical events](../src/metricon/schema/events.py), [bounded adapters](../src/metricon/ingest/adapters.py), original browser compatibility, quality/rejection/conflict records, [integrity and drift audits](../src/metricon/quality/audit.py). |
| Storage and tasks | [Immutable partition/catalog publication](../src/metricon/storage/catalog.py), checksummed source references, exact identity indexes, coordinator-owned publication, bounded processes, cancellation, wall budgets and restart recovery. See the [runbook](TASKS.md). |
| Analytics and features | [DuckDB/Polars aggregates](../src/metricon/analytics/engine.py), real denominators, uncertainty, scoped durations, pagination and versioned caches; [as-of history](../src/metricon/features/history.py), whole-unit splits and complete fitting scopes. |
| Models and evaluation | Constant/item/recent/logistic baselines, fitted BKT, hierarchical performance and eligible 1PL/2PL cohort IRT; [frozen predictions, calibration, cluster uncertainty and ablations](../src/metricon/evaluation/experiment.py). |
| Planning and simulation | [Observed-support action ranking](../src/metricon/recommendation/planner.py), priorities/prerequisites and honest time eligibility; seeded matched-budget simulation, complete trajectories and a misspecified regime. |
| API, CLI and workbench | [Loopback API](../src/metricon/api/app.py), [packaged CLI](../src/metricon/cli/main.py), runtime-validated React client, import inspection, run comparison, model replay, lineage, task controls, exports and accessible responsive views. |

The original sample typing failure, invented peer benchmarks, cumulative-success streak and automatic demonstration import were removed. Empty workspaces stay empty. Last correctness does not certify mastery. The [schema](SCHEMA.md), [metric glossary](METRICS.md), [model cards](MODEL_CARDS.md) and [ADRs](adrs) define the replacements.

## Command evidence

Locked Python and Node installs, lint, strict TypeScript, production client/wheel builds and browser verification passed. The final fast campaign reports 100 Python tests, 10 client unit tests and 66 browser cases. One upstream Starlette/AnyIO deprecation warning remains visible.

| Command | Recorded outcome |
| --- | --- |
| `uv sync --locked` | Passed; `.metricon/verification/commands/python-install.json` and its raw log. |
| `npm ci` | Passed; `.metricon/verification/commands/node-install.json` and its raw log. |
| `ruff check src tests scripts` | Passed; `.metricon/verification/commands/lint.json` and its raw log. |
| `pytest -q` | Passed; `.metricon/verification/commands/python-tests.json` and its raw log. |
| `npm run check` | Passed; `.metricon/verification/commands/typescript.json` and its raw log. |
| `npm run test:web` | Passed; `.metricon/verification/commands/web-tests.json` and its raw log. |
| `npm run build` | Passed; `.metricon/verification/commands/production-build.json` and its raw log. |
| `uv build --wheel` | Passed; `.metricon/verification/commands/api-build.json` and its raw log. |
| `npm run test:e2e` | Passed; `.metricon/verification/commands/browser.json` and its raw log. |
| `make bootstrap` | Locked environment, client and wheel built. Installed-wheel smoke checks fitted baseline/BKT/IRT families; the final wheel retained the exact lock and served HTTP 200 for all seven client sections. |
| `make dev`, `make demo` | Local API/client startup and explicit demo creation exercised. Startup failure propagates and owned process groups are cleaned up. |
| `make test-integration` | Independent import, analytical and interruption campaigns completed; final acceptance reran or checked their source-matched evidence. |
| CLI walkthrough | 23 actual commands exercised import/retry/rejection, analysis, fitting, forward/learner-held-out/rolling evaluation, paired comparison, planning, simulation and all four export formats. Expected invalid validation returned nonzero. |
| `make acceptance` | All correctness gates passed; predictive targets true, performance targets false. |
| `make verify` | Existing files, source, locks, datasets, scopes, frozen predictions, corpus checksums and gates verified without regeneration. |

A changed raw evidence log was deliberately rejected by verification, then restored byte-for-byte. Historical failed runner, memory and source-change campaigns remain retained locally. The [review](reports/REVIEW.md) records the discovered causes and regression evidence.

## Required workloads

| Workload | Final evidence |
| --- | --- |
| Import correctness | 10,000 generated cases; normalized content/counts match an independent reference, retry is idempotent. |
| Analytical correctness | 1,000 generated datasets against independent Python histories and Polars, including empty/all-correct/all-incorrect and mixed duration scopes. |
| Crash safety | 100 real interruption/restart cases around import/artifact publication; no half-visible dataset. |
| Scale | Five repetitions each at 100,000, 1,000,000 and 10,000,000 records; exact independent contents/counts and import peak RSS below 2 GiB. |
| Model fitting | Independent scalar BKT updates, finite-difference fitting checks, saved parameter round trips, eligible public-cohort IRT and 15 supported-history fitting repetitions. |
| Leakage and evaluation | Planted future features/dependencies, fitting overlap and overlapping temporal splits rejected; complete preprocessing scopes and frozen metrics independently recomputed. |
| Public research | 200,653 EdNet KT1 interactions from 1,268 learners, complete eligible histories, verified archive/content/subset provenance. |
| Simulation | 1,200 policy outcomes and 18,000 trajectory events: four regimes, five policies, two budget modes and 30 seeds per cell. |
| Product | Import/rejections, actual fitting, run comparison/calibration, saved mechanics, planning/simulation, running cancellation, exports, lineage, keyboard tables and mobile rendering. |

## Findings and measured limits

The [research report](reports/RESEARCH.md) retains every baseline, calibration and ablation. On 42,960 common held-out EdNet targets, validation-selected logistic C=1 scored 0.549014 raw log loss, BKT 0.597889 and the constant 0.627377. Both uncalibrated cohort IRT variants fitted and scored worse than the constant; validation calibration improved their probability quality. Five fixed identifiable synthetic datasets showed BKT relative improvements of 33.48 to 36.57 percent. Simulation intervals include zero and do not establish a policy benefit.

The [performance report](reports/PERFORMANCE.md) records every repetition and source snapshot. At ten million input records, median canonical import throughput was 22,215 records/second, maximum import RSS 1.241 GiB and worst measured common query p95 281.722 ms. The 50,000 records/second throughput objective failed; the 500 ms query objective passed on this workstation profile. Cold means connection-cold, with no OS cache flush.

Actual [figures](figures) link to raw figure data and immutable run IDs. [Workbench screenshots](WORKBENCH.md) show the running API-backed application, including readable stacked mobile learner controls. The scientific claims depend on recorded computations, not the screenshots.

## Evidence and next action

Accepted source/test/lock hash: `14e2cd863c59bd698bb4e337b816299d1445c8de2fcc2273e1ef16d42eb572e4`. The full `.metricon/verification/ACCEPTANCE.json` indexes 2,454 evidence files and the exact run artifacts. Raw predictions, dependency locks, source snapshots, split/feature scopes, bootstrap seeds, benchmark profiles and simulation traces remain in ignored local storage.

Incomplete required correctness gates: none. The remaining measured optimization objective is import throughput. Reproduce `make acceptance` and `make verify` before comparing a changed implementation. Changes to data or transformation contracts require new dependent artifacts and fresh verification; existing results remain immutable.
