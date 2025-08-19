from __future__ import annotations

import contextlib
import hashlib
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from metricon.analytics.engine import Analytics
from metricon.analytics.exports import export_dataset
from metricon.analytics.sessions import sessions
from metricon.quality.drift import DriftConfig, drift_report
from metricon.api.contracts import (
    DemoRequest,
    ExperimentRequest,
    ImportJobRequest,
    ImportOptionsRequest,
    JobResponse,
    PlannerRequest,
    SimulationRequest,
    WorkspaceRequest,
    WorkspaceResponse,
)
from metricon.evaluation.experiment import ExperimentConfig
from metricon.evaluation.comparison import compare_runs
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.demo import demo_workspace
from metricon.ingest.pipeline import preview, reconcile
from metricon.tasks.coordinator import JobCoordinator
from metricon.quality.audit import dataset_audit
from metricon.recommendation.planner import PlannerConfig, plan
from metricon.schema.events import AttemptEvent
from metricon.simulation.engine import SimulationConfig
from metricon.storage.artifacts import verify_artifact
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json, file_hash, read_json


class Settings:
    def __init__(
        self,
        root: Path | None = None,
        maximum_upload_bytes: int = 2_000_000_000,
        web_directory: Path | None = None,
    ):
        self.root = (root or Path(os.environ.get("METRICON_HOME", ".metricon"))).resolve()
        self.maximum_upload_bytes = maximum_upload_bytes
        packaged = Path(__file__).parents[1] / "web_dist"
        self.web_directory = web_directory or (
            packaged if packaged.is_dir() else Path(__file__).parents[3] / "web" / "dist"
        )


def create_app(settings: Settings | None = None, start_jobs: bool = True) -> FastAPI:
    settings = settings or Settings()
    catalog = Catalog(settings.root)
    coordinator = JobCoordinator(catalog)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_jobs:
            reconcile(catalog)
            coordinator.start()
        yield
        if start_jobs:
            coordinator.close()

    app = FastAPI(
        title="Metricon Laboratory",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.catalog = catalog
    app.state.coordinator = coordinator
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Metricon-Client"],
    )

    @app.middleware("http")
    async def local_write_guard(request: Request, call_next: Any):
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.headers.get("X-Metricon-Client") != "1"
        ):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {"detail": "Local writes require X-Metricon-Client: 1"}, status_code=403
            )
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(KeyError)
    async def missing(request: Request, error: KeyError):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": str(error.args[0])}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request: Request, error: ValueError):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": str(error)}, status_code=422)

    def uploaded(identifier: str) -> Path:
        if len(identifier) != 64 or any(char not in "0123456789abcdef" for char in identifier):
            raise HTTPException(422, "Invalid upload identifier")
        path = catalog.root / "uploads" / identifier
        if not path.is_file():
            raise HTTPException(404, "Upload does not exist")
        return path

    def committed_file(identifier: str, filename: str) -> Path:
        artifact = catalog.artifact(identifier)
        expected = artifact["manifest"]["files"].get(filename)
        if expected is None:
            raise HTTPException(404, "File not in committed artifact")
        directory = (catalog.root / "artifacts" / identifier).resolve()
        path = (directory / filename).resolve()
        if not path.is_relative_to(directory):
            raise HTTPException(404, "File outside committed artifact")
        if not path.is_file() or file_hash(path) != expected:
            raise HTTPException(409, "Committed artifact checksum mismatch or missing file")
        return path

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "2.0.0",
            "schema_version": "attempt/1",
            "coordinator_running": coordinator.thread is not None and coordinator.thread.is_alive(),
        }

    @app.get("/api/experiments")
    def all_experiments() -> list[dict[str, Any]]:
        with catalog.connect() as connection:
            rows = connection.execute(
                "SELECT a.id,a.dataset_id,a.created_at,w.name workspace_name,w.kind workspace_kind FROM artifact a JOIN dataset d ON d.id=a.dataset_id JOIN workspace w ON w.id=d.workspace_id WHERE a.kind='experiment' ORDER BY a.created_at DESC LIMIT 200"
            ).fetchall()
        return [dict(row) for row in rows]

    @app.get("/api/compare")
    def comparison(
        left: str,
        right: str,
        left_model: str = "bkt",
        right_model: str = "global",
        fold: int = Query(0, ge=0, le=9),
    ) -> dict[str, Any]:
        return compare_runs(catalog, left, right, left_model, right_model, fold)

    @app.get("/api/schema")
    def schema() -> dict[str, Any]:
        return AttemptEvent.model_json_schema()

    @app.get("/api/workspaces", response_model=list[WorkspaceResponse])
    def workspaces() -> list[dict[str, Any]]:
        return catalog.workspaces()

    @app.post("/api/workspaces", response_model=WorkspaceResponse, status_code=201)
    def create_workspace(body: WorkspaceRequest) -> dict[str, Any]:
        return catalog.create_workspace(body.name, body.kind)

    @app.post("/api/demo", status_code=201)
    def create_demo(body: DemoRequest) -> dict[str, Any]:
        return demo_workspace(catalog, body.seed, body.learners, body.attempts)

    @app.get("/api/workspaces/{workspace_id}", response_model=WorkspaceResponse)
    def workspace(workspace_id: str) -> dict[str, Any]:
        return catalog.workspace(workspace_id)

    @app.get("/api/workspaces/{workspace_id}/datasets")
    def datasets(workspace_id: str) -> list[dict[str, Any]]:
        catalog.workspace(workspace_id)
        return catalog.datasets(workspace_id)

    @app.post("/api/uploads", status_code=201)
    async def upload(file: UploadFile) -> dict[str, Any]:
        directory = catalog.root / "uploads"
        directory.mkdir(exist_ok=True)
        temporary = directory / ("upload-" + uuid.uuid4().hex)
        sha = hashlib.sha256()
        count = 0
        try:
            with temporary.open("wb") as handle:
                while chunk := await file.read(1024 * 1024):
                    count += len(chunk)
                    if count > settings.maximum_upload_bytes:
                        raise HTTPException(413, "Upload exceeds configured byte bound")
                    sha.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            identifier = sha.hexdigest()
            destination = directory / identifier
            if destination.exists():
                temporary.unlink()
            else:
                os.rename(temporary, destination)
            metadata = {
                "upload_id": identifier,
                "bytes": count,
                "filename": (file.filename or "source")[:512],
                "sha256": identifier,
            }
            atomic_json(directory / f"{identifier}.json", metadata)
            return metadata
        finally:
            temporary.unlink(missing_ok=True)
            await file.close()

    @app.post("/api/uploads/{upload_id}/preview")
    def preview_upload(
        upload_id: str, body: ImportOptionsRequest, limit: int = Query(20, ge=1, le=1000)
    ) -> dict[str, Any]:
        path = uploaded(upload_id)
        if file_hash(path) != upload_id:
            raise ValueError("Uploaded file checksum changed")
        return preview(path, AdapterOptions(**body.model_dump()), limit)

    @app.post("/api/workspaces/{workspace_id}/import", response_model=JobResponse, status_code=202)
    def queue_import(workspace_id: str, body: ImportJobRequest) -> dict[str, Any]:
        uploaded(body.upload_id)
        return coordinator.submit(workspace_id, "import", body.model_dump())

    @app.post(
        "/api/workspaces/{workspace_id}/experiments", response_model=JobResponse, status_code=202
    )
    def queue_experiment(
        workspace_id: str, body: ExperimentRequest, dataset_id: str | None = None
    ) -> dict[str, Any]:
        ExperimentConfig(**body.model_dump()).validate()
        return coordinator.submit(workspace_id, "experiment", body.model_dump(), dataset_id)

    @app.post(
        "/api/workspaces/{workspace_id}/simulations", response_model=JobResponse, status_code=202
    )
    def queue_simulation(
        workspace_id: str, body: SimulationRequest, dataset_id: str | None = None
    ) -> dict[str, Any]:
        SimulationConfig(**body.model_dump()).validate()
        return coordinator.submit(workspace_id, "simulation", body.model_dump(), dataset_id)

    @app.get("/api/workspaces/{workspace_id}/jobs", response_model=list[JobResponse])
    def jobs(workspace_id: str, limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
        catalog.workspace(workspace_id)
        return coordinator.list(workspace_id, limit)

    @app.get("/api/jobs/{job_id}", response_model=JobResponse)
    def job(job_id: str) -> dict[str, Any]:
        return coordinator.get(job_id)

    @app.post("/api/jobs/{job_id}/cancel", response_model=JobResponse)
    def cancel(job_id: str) -> dict[str, Any]:
        return coordinator.cancel(job_id)

    @app.get("/api/datasets/{dataset_id}")
    def dataset(dataset_id: str) -> dict[str, Any]:
        result = catalog.dataset(dataset_id)
        manifest = result["manifest"]
        return {
            "id": result["id"],
            "workspace_id": result["workspace_id"],
            "parent_id": result["parent_id"],
            "row_count": result["row_count"],
            "created_at": result["created_at"],
            "schema_version": manifest["schema_version"],
            "source": manifest["source"],
            "quality": manifest["quality"],
            "partition_count": len(manifest["partitions"]),
        }

    @app.get("/api/datasets/{dataset_id}/audit")
    def audit(dataset_id: str, verify_checksums: bool = False) -> dict[str, Any]:
        return dataset_audit(catalog, dataset_id, verify_checksums)

    @app.get("/api/datasets/{dataset_id}/overview")
    def overview(dataset_id: str, learner_id: str | None = None) -> dict[str, Any]:
        return Analytics(catalog, dataset_id).cached_overview({"learner_id": learner_id})

    @app.get("/api/datasets/{dataset_id}/groups")
    def groups(
        dataset_id: str,
        dimension: str = "question",
        learner_id: str | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=500),
        search: str = "",
    ) -> dict[str, Any]:
        return Analytics(catalog, dataset_id).groups(dimension, offset, limit, learner_id, search)

    @app.get("/api/datasets/{dataset_id}/history")
    def history(
        dataset_id: str,
        learner_id: str,
        question_id: str | None = None,
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        return Analytics(catalog, dataset_id).history(learner_id, question_id, limit, offset)

    @app.get("/api/datasets/{dataset_id}/sessions")
    def session_history(
        dataset_id: str,
        learner_id: str | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=500),
    ) -> dict[str, Any]:
        return sessions(catalog, dataset_id, learner_id, offset, limit)

    @app.get("/api/datasets/{dataset_id}/streaks")
    def streaks(dataset_id: str, learner_id: str) -> dict[str, Any]:
        return Analytics(catalog, dataset_id).streaks(learner_id)

    @app.get("/api/datasets/{dataset_id}/trend")
    def trend(
        dataset_id: str,
        learner_id: str,
        bins: int = Query(80, ge=2, le=500),
        axis: str = "order",
        question_id: str | None = None,
    ) -> dict[str, Any]:
        return Analytics(catalog, dataset_id).trend(learner_id, bins, axis, question_id)

    @app.get("/api/datasets/{dataset_id}/cohort")
    def cohort(
        dataset_id: str, learner_id: str, minimum_attempts: int = Query(20, ge=1)
    ) -> dict[str, Any]:
        return Analytics(catalog, dataset_id).cohort(learner_id, minimum_attempts)

    @app.post("/api/datasets/{dataset_id}/plan")
    def planner(dataset_id: str, body: PlannerRequest) -> dict[str, Any]:
        parameters = body.model_dump(exclude={"learner_id"})
        return plan(catalog, dataset_id, body.learner_id, PlannerConfig(**parameters))

    @app.post("/api/datasets/{dataset_id}/export")
    def export(
        dataset_id: str, format: str = "json", learner_id: str | None = None
    ) -> dict[str, Any]:
        identifier = export_dataset(catalog, dataset_id, format, learner_id)
        return {
            "artifact_id": identifier,
            "dataset_id": dataset_id,
            "filename": f"events.{format}",
            "download_url": f"/api/artifacts/{identifier}/files/events.{format}",
        }

    @app.get("/api/datasets/{dataset_id}/drift")
    def drift(
        dataset_id: str,
        learner_id: str,
        window_events: int = Query(100, ge=30, le=10000),
        artifact_id: str | None = None,
        model: str = "bkt",
    ) -> dict[str, Any]:
        return drift_report(
            catalog,
            dataset_id,
            learner_id,
            DriftConfig(window_events=window_events, minimum_events=min(50, window_events)),
            artifact_id,
            model,
        )

    @app.get("/api/datasets/{dataset_id}/artifacts")
    def artifacts(dataset_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        catalog.dataset(dataset_id)
        return catalog.artifacts(dataset_id, kind)

    @app.get("/api/artifacts/{artifact_id}")
    def artifact(artifact_id: str) -> dict[str, Any]:
        result = catalog.artifact(artifact_id)
        return {
            "id": artifact_id,
            "kind": result["kind"],
            "dataset_id": result["dataset_id"],
            "manifest": result["manifest"],
            "lineage": catalog.ancestors(artifact_id),
        }

    @app.get("/api/artifacts/{artifact_id}/verify")
    def verify(artifact_id: str) -> dict[str, Any]:
        return verify_artifact(catalog, artifact_id)

    @app.get("/api/artifacts/{artifact_id}/report")
    def report(artifact_id: str, full: bool = False) -> dict[str, Any]:
        metadata = catalog.artifact(artifact_id)
        if metadata["kind"] not in {"experiment", "simulation"}:
            raise ValueError("Artifact has no research report")
        filename = "report.json" if metadata["kind"] == "experiment" else "simulation.json"
        payload = read_json(committed_file(artifact_id, filename))
        if full or metadata["kind"] == "simulation":
            return payload
        for fold in payload["folds"]:
            for model in fold["models"].values():
                model.pop("slices", None)
        return payload

    @app.get("/api/artifacts/{artifact_id}/files/{filename:path}")
    def download_artifact(artifact_id: str, filename: str) -> FileResponse:
        path = committed_file(artifact_id, filename)
        return FileResponse(path, filename=Path(filename).name)

    @app.get("/api/artifacts/{artifact_id}/models/{name}/parameters")
    def model_parameters(
        artifact_id: str, name: str, fold: int = Query(0, ge=0, le=9)
    ) -> dict[str, Any]:
        filename = f"fold-{fold}/{name}.model.json"
        payload = read_json(committed_file(artifact_id, filename))
        parameters = payload["parameters"]
        if parameters["family"] == "logistic":
            from metricon.models.baselines import LogisticHistory

            parameters["associations"] = LogisticHistory.restore(parameters).associations()
        return parameters

    @app.get("/api/lineage/{identifier}")
    def lineage_graph(identifier: str) -> dict[str, Any]:
        from metricon.storage.lineage import LineageGraph

        catalog.artifact(identifier)
        return LineageGraph(catalog).graph(identifier)

    @app.get("/api/lineage/{identifier}/verify")
    def verify_lineage(identifier: str) -> dict[str, Any]:
        from metricon.storage.lineage import LineageGraph

        return LineageGraph(catalog).verify(identifier)

    @app.get("/api/lineage/{identifier}/descendants")
    def lineage_descendants(identifier: str) -> dict[str, Any]:
        from metricon.storage.lineage import LineageGraph

        return {
            "source": identifier,
            "dependent_nodes": LineageGraph(catalog).descendants(identifier),
        }

    @app.get("/api/artifacts/{artifact_id}/models/{name}/replay")
    def model_replay(
        artifact_id: str,
        name: str,
        learner_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        fold: int = Query(0, ge=0, le=9),
    ) -> dict[str, Any]:
        from metricon.models.trace import replay_bkt

        committed_file(artifact_id, f"fold-{fold}/{name}.model.json")
        return replay_bkt(catalog, artifact_id, name, learner_id, offset, limit, fold)

    @app.get("/api/artifacts/{artifact_id}/predictions")
    def prediction_rows(
        artifact_id: str,
        model: str,
        partition: str = "test",
        learner_id: str | None = None,
        question_id: str | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=500),
        sort: str = "identity",
        fold: int = Query(0, ge=0, le=9),
    ) -> dict[str, Any]:
        from metricon.evaluation.predictions import PredictionInspector

        committed_file(artifact_id, f"fold-{fold}/predictions.parquet")
        return PredictionInspector(catalog, artifact_id, fold).rows(
            model, partition, learner_id, question_id, offset, limit, sort
        )

    @app.get("/api/artifacts/{artifact_id}/prediction-slice")
    def prediction_slice(
        artifact_id: str,
        model: str,
        learner_id: str | None = None,
        skill: str | None = None,
        calibrated: bool = False,
        fold: int = Query(0, ge=0, le=9),
    ) -> dict[str, Any]:
        from metricon.evaluation.predictions import PredictionInspector

        committed_file(artifact_id, f"fold-{fold}/predictions.parquet")
        return PredictionInspector(catalog, artifact_id, fold).slice(
            model, learner_id, skill, calibrated
        )

    if settings.web_directory.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_directory, html=True), name="workbench")
    return app
