# Reproduce experiments and inspect evidence

Use Python 3.13, Node 24 and uv with the checked-in Python and Node locks. `make bootstrap` installs locked dependencies and builds the wheel and browser client. `make dev` starts the local API and Vite development server, while the production service serves the compiled client from port 8000. `make demo` explicitly creates a separate synthetic workspace.

```bash
make bootstrap
make test
make test-integration
make test-e2e
make dataset-public
make experiment
make benchmark
make acceptance
make verify
```

The benchmark and full scientific campaign take materially longer than fast checks. Preserve the local evidence directory across interruptions. Make targets use `.metricon` by default; `METRICON_ROOT=/absolute/path` selects another catalog for data/research commands. The browser acceptance server has its own local fixture store.

`make experiment` uses the recorded public dataset when present and otherwise creates an explicit synthetic workspace. The CLI `train DATASET --split forward|learner|rolling` chooses the evaluation question. All preprocessing and item priors fit training only. A fixed validation partition selects logistic regularization and calibration. Final test rows are excluded from every fitting/selection scope. Sessions, bundles and timestamp ties are coupled units; rolling folds preserve the same restriction.

Experiment artifacts contain:

- Canonical dataset ID, split assignments and hashes, fitting scopes and feature contract.
- Exact fitted model parameters and warm training state, calibration parameters and diagnostics.
- Raw validation/test probabilities, observed labels and target identities in Parquet.
- Uncalibrated and calibrated metrics, class balance, eligibility, cold/warm and skill/learner slices.
- Whole learner-cluster intervals and paired comparison seeds/repetition counts.
- Pipeline source snapshot, dependency lock, environment versions, runtime and process-lifetime peak RSS.

Predictions are frozen before reports are compared. `metricon evaluate RUN` recomputes metrics from hashed prediction files without fitting. `metricon compare LEFT RIGHT` uses paired resampling only when both runs share dataset, split and target population; otherwise it labels the comparison descriptive. A lower score on a different population cannot establish a better model.

Artifact IDs hash their file manifest and metadata. Lineage tracks source files, canonical partitions, normalization contracts, dataset versions, split scope, feature/environment files, models, calibration, predictions and reports. Logical split nodes include the dataset identity so equivalent assignments from unrelated datasets cannot collide. A changed dependency belongs to a new run. Old artifacts remain inspectable rather than being overwritten with updated results.

`make acceptance` executes installs, builds, tests, adversarial imports, analytical references, actual crash/restarts, all scale sizes/repetitions, fixed synthetic comparisons, public research, simulation and browser flows. It writes command logs and raw evidence before assessing gates. Correctness, predictive quality and throughput targets have separate fields; a weak model or slow import is not rewritten into success. Interrupted and failed command/worker logs remain retained. Completed synthetic cache entries are reusable only for the recorded pipeline source hash.

`make verify` validates existing file hashes, source/test/lock contents, run artifacts, fitting scopes and recomputed frozen metrics. It never regenerates missing evidence. Editing accepted source invalidates its source snapshot. Copying screenshots cannot satisfy data/model/research gates.

## Evidence locations

| Local path | Meaning |
| --- | --- |
| `.metricon/verification/commands` | Actual command arguments, exits, elapsed time and raw output. |
| `.metricon/verification/ingestion` | Generated corruption/identity corpus and independent count/content comparison. |
| `.metricon/verification/analytics` | Independent Python and Polars comparisons and per-case corpus hashes. |
| `.metricon/verification/recovery` | Real child-process termination points, restart visibility, cleanup and retry. |
| `.metricon/benchmark` | Hashed scale corpora, raw repetitions, profiles, source snapshots and timing distributions. |
| `.metricon/verification/synthetic` | Five fixed known-process datasets and model comparisons. |
| `.metricon/verification/research` | Public subset, provenance and frozen research verification. |
| `.metricon/verification/simulation` | Seeded regime comparisons, outcome Parquet and complete trajectories. |
| `.metricon/verification/browser` | Actual browser results, screenshots and retained failure traces. |
| `.metricon/verification/ACCEPTANCE.json` | The final evidence index and separate correctness/quality/performance outcomes. |

The default local workflow needs no hosted service or model API. CI runs fast checks and browser flows on pull requests; the separate manual/monthly workflow runs the research and scale campaign. Dataset access and hardware timing can differ. Raw public learner records are not uploaded by those workflows.
