# Metricon

Metricon connects immutable practice records, uncertainty, calibrated prediction, and inspectable study decisions. It runs locally with Python, SQLite, Parquet, DuckDB, Polars, and a React scientific workbench.

An imported answer is an observation. The last correct answer is not confirmed mastery. Legacy browser exports have no timestamps, so their charts show question-local event order. Empty accounts stay empty; demonstration datasets require an explicit action and have separate storage.

## Run locally

Requires Python 3.13, Node 24, and uv. Dependencies are locked in `uv.lock` and `package-lock.json`.

```bash
uv sync --locked --extra dev
npm ci
npm run build
uv run metricon serve --port 8000
```

Open http://127.0.0.1:8000. Create a workspace, preview a file, inspect its quality warnings, and submit the import. The explicit demo action creates a synthetic workspace. The service binds to loopback by default.

```bash
uv run metricon demo
uv run metricon --help
uv run pytest -q
uv run ruff check src tests
npm run check
npm run test:web
```

## Implemented behavior

- Streaming JSON, legacy question-keyed JSON, CSV, NDJSON, and Parquet adapters validate strict booleans, stable identities, timestamps, and duration scope. Duplicate attempts are idempotent; changed content under the same identity is quarantined as a conflict.
- Immutable Parquet partitions and transactional SQLite manifest pointers preserve the previous dataset until a complete import is committed. Independent DuckDB connections scan committed files.
- Aggregates report eligible counts, Wilson intervals, first-attempt and all-attempt accuracy, actual streaks, retry censoring, and known-duration distributions. Cohort panels require observed peers.
- Training includes constant, item-prior, recent-history, logistic, hierarchical Beta-Binomial, fitted BKT, and eligible regularized cohort IRT models. Predictions precede answers. Temporal splits keep coupled sessions together.
- Experiments preserve predictions, parameters, validation-only calibration, cluster bootstrap uncertainty, diagnostics, and source snapshots. The workbench exposes model mechanics, lineage, held-out errors, recommendations, and conditional simulations.

## Reproduction and current evidence

The [build status](docs/BUILD_STATUS.md) records implemented behavior and outstanding verification. The [architecture](docs/ARCHITECTURE.md) describes ownership and publication boundaries. Research outputs and imported public records live in ignored local storage. EdNet KT1 is used under its research license; raw learner records are not distributed here.

The local EdNet subset contains 200,653 valid interactions from 1,268 learners. Its first experiment completed; final research review, scale measurements, and full acceptance remain in progress. A passing build is not research validation.

MIT applies to Metricon source. Public datasets retain their own terms.
