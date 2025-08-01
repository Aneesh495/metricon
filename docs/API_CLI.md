# API and CLI reference

`metricon --root PATH` selects an independent local catalog. All command output uses explicit dataset/run identifiers. The CLI is [implemented here](../src/metricon/cli/main.py); its `--help` is authoritative for options. `validate`, `audit`, artifact verification and acceptance verification return nonzero on invalid evidence or data.

## A working local sequence

```bash
make bootstrap
.venv/bin/metricon demo --learners 50 --attempts 90 > .metricon/demo-result.json
DATASET=$(.venv/bin/python -c 'import json; print(json.load(open(".metricon/demo-result.json"))["workspace"]["dataset_id"])')
.venv/bin/metricon analyze "$DATASET"
.venv/bin/metricon train "$DATASET" > .metricon/train-result.json
RUN=$(.venv/bin/python -c 'import json; print(json.load(open(".metricon/train-result.json"))["artifact_id"])')
.venv/bin/metricon evaluate "$RUN"
.venv/bin/metricon compare "$RUN" "$RUN" --left-model bkt --right-model global
.venv/bin/metricon recommend "$DATASET" demo-000 --budget 900 --run "$RUN"
.venv/bin/metricon export "$DATASET" --format csv --output .metricon/demo-export.csv
```

For an existing browser export:

```bash
.venv/bin/metricon workspace "Practice records" > .metricon/workspace-result.json
WORKSPACE=$(.venv/bin/python -c 'import json; print(json.load(open(".metricon/workspace-result.json"))["id"])')
.venv/bin/metricon validate practice.json --format legacy --namespace practice --learner local
.venv/bin/metricon ingest practice.json --format legacy --namespace practice --learner local --workspace "$WORKSPACE"
```

`preview` samples a prefix; `validate` checks the whole file. Canonical formats are `json`, `csv`, `ndjson` and `parquet`. A canonical file's namespace must match the selected namespace. Original browser records retain question-local ordering. The browser migration flow reads the original `quizSubmissions` key only after explicit action, previews it and provides a backup before import.

| Command | Result |
| --- | --- |
| `ingest FILE --workspace ID` | Immutable dataset publication and exact import/quality report. `import` remains an alias. |
| `validate FILE` | Full independent temporary import, errors/conflicts and a validity exit status. |
| `analyze DATASET [--learner ID]` | Eligible aggregates and uncertainty. `overview` remains available. |
| `audit DATASET --checksums` | Counts, identities, missingness, ordering warnings and partition integrity. |
| `train DATASET --split forward` | Fitted experiment with raw predictions, parameters, diagnostics and reports. `experiment` remains available. |
| `evaluate RUN` | Recomputed frozen test metrics, with no refit. |
| `compare LEFT RIGHT` | Actual same-row paired or explicitly descriptive comparison. |
| `simulate --config FILE --output FILE` | Seeded conditional policy outcomes and configuration hash. Default config also works. |
| `recommend DATASET LEARNER --budget 900` | Ranked observed-history actions, time eligibility and factor contributions. |
| `export DATASET --format parquet` | Hashed immutable export plus its exact dataset ID. |
| `reconcile` | Orphan cleanup under exclusive local ownership locks. Stop the service first. |
| `verify-artifact RUN` | Artifact identity, manifest and file checksums. |
| `acceptance`, `verify` | Generate the full evidence campaign, or validate existing evidence without generation. |

`serve --port 8000` always binds loopback. `make dev` also starts Vite at port 5173. No remotely accessible multi-user mode is implemented.

## Local HTTP contract

The [FastAPI routes](../src/metricon/api/app.py) and [Pydantic request types](../src/metricon/api/contracts.py) generate the current OpenAPI reference at `/api/docs`. The [workbench client](../web/src/api/client.ts) validates responses through [Zod contracts](../web/src/api/contracts.ts). Unknown data and explicit unavailable results remain distinct from zero.

Every write requires `X-Metricon-Client: 1`. CORS permits the local Vite origin; host checks reject unrelated hostnames. This protects the local browser workflow against ordinary cross-origin form writes. It is not a substitute for remote authentication. Uploads are bounded, checksummed local files; the API accepts upload IDs instead of arbitrary server file paths.

| Routes | Behavior |
| --- | --- |
| `GET /api/health`, `/api/schema` | Local service/storage mode and canonical schema. |
| `GET/POST /api/workspaces`, `GET /api/workspaces/{id}` | Explicit workspace creation and selection. Blank workspaces have null dataset pointers. |
| `POST /api/demo` | Explicit separately labeled synthetic workspace. |
| `POST /api/uploads`, `/api/uploads/{hash}/preview` | Multipart source upload and sampled schema/quality inspection. |
| `POST /api/workspaces/{id}/import`, `/experiments`, `/simulations` | Persistent task submission, HTTP 202. |
| `GET /api/workspaces/{id}/jobs`, `/api/jobs/{id}` | Actual task states, completed work, errors and result IDs. |
| `POST /api/jobs/{id}/cancel` | Cooperative cancellation and bounded process termination. |
| `GET /api/datasets/{id}/overview`, `/groups`, `/history` | Real aggregates, filtered/paginated groups and observations. |
| `GET /api/datasets/{id}/sessions`, `/streaks`, `/trend`, `/cohort`, `/drift` | Eligible session/order/time/cohort summaries and actual-window diagnostics. |
| `POST /api/datasets/{id}/plan`, `/export` | Inspectable recommendations and exact-version exports. |
| `GET /api/experiments`, `/api/compare` | Saved run selection and actual comparisons. |
| `GET /api/artifacts/{id}/report`, `/verify`, `/files/{name}` | Reports and checksum-protected immutable files. Only manifested files are downloadable. |
| `GET /api/artifacts/{id}/models/{name}/parameters`, `/replay` | Saved model mechanics and explicitly retrospective state replay. |
| `GET /api/artifacts/{id}/predictions`, `/prediction-slice` | Paginated frozen probability errors and aggregate slices. |
| `GET /api/lineage/{id}`, `/verify`, `/descendants` | Dependency DAG, file integrity and affected descendants. |

Groups accept dimension, search, learner, offset and limit. History and prediction endpoints cap page size. Chart endpoints cap bins and retain denominators/extrema. Invalid choices return 422; unknown identifiers return 404. Unexpected failures remain visible and are not converted to empty successful charts. Task exceptions retain tracebacks and do not publish a success result.

Exports contain accepted canonical observations only, with an exact-version manifest. CSV literal encoding protects spreadsheet-active strings while retaining round-trip meaning. Parquet/JSON/NDJSON preserve raw values. Download routes verify file hashes and reject paths outside the artifact directory.
