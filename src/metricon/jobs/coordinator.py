from __future__ import annotations

import fcntl
import json
import threading
import time
import traceback
import uuid
from typing import Any

from metricon.analytics.engine import Analytics
from metricon.evaluation.experiment import ExperimentConfig, run_experiment
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.pipeline import import_file
from metricon.schema.events import canonical_json
from metricon.simulation.engine import SimulationConfig, simulate
from metricon.storage.artifacts import ArtifactWriter
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json, file_hash

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}


class JobCoordinator:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.thread: threading.Thread | None = None
        self.owner: Any = None

    def start(self) -> None:
        path = self.catalog.root / "locks" / "coordinator.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.owner = path.open("a")
        try:
            fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.owner.close()
            raise RuntimeError("This workspace already has a job coordinator")
        with self.catalog.transaction() as connection:
            connection.execute(
                "UPDATE job SET status='interrupted',error='Coordinator stopped before publication; resubmit explicitly',updated_at=? WHERE status='running'",
                (time.time(),),
            )
        self.thread = threading.Thread(target=self._loop, name="metricon-coordinator", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.stop_event.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=30)
        if (
            self.owner
            and not self.owner.closed
            and (self.thread is None or not self.thread.is_alive())
        ):
            fcntl.flock(self.owner, fcntl.LOCK_UN)
            self.owner.close()

    def submit(
        self,
        workspace_id: str,
        kind: str,
        parameters: dict[str, Any],
        dataset_id: str | None = None,
    ) -> dict[str, Any]:
        if kind not in {"import", "experiment", "analytics", "simulation"}:
            raise ValueError("Unknown job kind")
        workspace = self.catalog.workspace(workspace_id)
        dataset = dataset_id or workspace["dataset_id"]
        if kind != "import" and dataset is None:
            raise ValueError("Import a dataset before submitting analytical jobs")
        if dataset is not None and self.catalog.dataset(dataset)["workspace_id"] != workspace_id:
            raise ValueError("Dataset does not belong to workspace")
        identifier = uuid.uuid4().hex
        now = time.time()
        with self.catalog.transaction() as connection:
            connection.execute(
                """
                INSERT INTO job(id,workspace_id,dataset_id,kind,parameters,status,created_at,updated_at)
                VALUES (?,?,?,?,?,'queued',?,?)
            """,
                (
                    identifier,
                    workspace_id,
                    dataset or "",
                    kind,
                    canonical_json(parameters),
                    now,
                    now,
                ),
            )
        self.wake.set()
        return self.get(identifier)

    def get(self, identifier: str) -> dict[str, Any]:
        with self.catalog.connect() as connection:
            row = connection.execute("SELECT * FROM job WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError("Job does not exist")
        result = dict(row)
        result["parameters"] = json.loads(result["parameters"])
        result["cancel_requested"] = bool(result["cancel_requested"])
        return result

    def list(self, workspace_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.catalog.connect() as connection:
            identifiers = [
                row[0]
                for row in connection.execute(
                    "SELECT id FROM job WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?",
                    (workspace_id, limit),
                )
            ]
        return [self.get(identifier) for identifier in identifiers]

    def cancel(self, identifier: str) -> dict[str, Any]:
        with self.catalog.transaction() as connection:
            row = connection.execute("SELECT status FROM job WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise KeyError("Job does not exist")
            if row["status"] not in TERMINAL:
                connection.execute(
                    "UPDATE job SET cancel_requested=1,updated_at=? WHERE id=?",
                    (time.time(), identifier),
                )
                if row["status"] == "queued":
                    connection.execute(
                        "UPDATE job SET status='cancelled',message='Cancelled before execution' WHERE id=?",
                        (identifier,),
                    )
        self.wake.set()
        return self.get(identifier)

    def _claim(self) -> dict[str, Any] | None:
        with self.catalog.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM job WHERE status='queued' AND cancel_requested=0 ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE job SET status='running',updated_at=? WHERE id=?", (time.time(), row["id"])
            )
        return self.get(row["id"])

    def _progress(self, identifier: str, progress: float, message: str) -> None:
        with self.catalog.transaction() as connection:
            connection.execute(
                "UPDATE job SET progress=?,message=?,updated_at=? WHERE id=?",
                (min(1, max(0, progress)), message[:2000], time.time(), identifier),
            )

    def _cancelled(self, identifier: str) -> bool:
        return self.stop_event.is_set() or self.get(identifier)["cancel_requested"]

    def _loop(self) -> None:
        try:
            while not self.stop_event.is_set():
                job = self._claim()
                if job is None:
                    self.wake.wait(1)
                    self.wake.clear()
                    continue
                self._execute(job)
        finally:
            if self.owner and not self.owner.closed:
                fcntl.flock(self.owner, fcntl.LOCK_UN)
                self.owner.close()

    def _execute(self, job: dict[str, Any]) -> None:
        identifier = job["id"]
        parameters = job["parameters"]

        def cancelled() -> bool:
            return self._cancelled(identifier)

        def progress(value: float, message: str) -> None:
            self._progress(identifier, value, message)

        try:
            if job["kind"] == "import":
                upload = self.catalog.root / "uploads" / parameters["upload_id"]
                if not upload.is_file() or file_hash(upload) != parameters["upload_id"]:
                    raise ValueError("Uploaded source is missing or its checksum changed")
                options = AdapterOptions(**parameters["options"])
                result = import_file(
                    self.catalog,
                    job["workspace_id"],
                    upload,
                    options,
                    progress=lambda count: progress(0, f"Processed {count} import records"),
                    cancelled=cancelled,
                )
                result_id = result["dataset_id"]
                message = canonical_json(result)
            elif job["kind"] == "experiment":
                config = ExperimentConfig(**parameters)
                result_id = run_experiment(
                    self.catalog, job["dataset_id"], config, progress, cancelled
                )
                message = "Experiment artifact published"
            elif job["kind"] == "analytics":
                result_id = Analytics(self.catalog, job["dataset_id"]).materialize(parameters)
                message = "Analytical artifact published"
            else:
                result = simulate(SimulationConfig(**parameters))
                if cancelled():
                    raise RuntimeError("Simulation cancelled before publication")
                with ArtifactWriter(self.catalog, "simulation", job["dataset_id"]) as writer:
                    atomic_json(writer.path / "simulation.json", result)
                    result_id = writer.publish({"configuration": parameters, "synthetic": True})
                message = "Synthetic simulation artifact published"
            status = "succeeded"
            error = None
        except Exception as exception:
            status = "cancelled" if cancelled() else "failed"
            result_id = None
            message = str(exception)[:2000]
            error = traceback.format_exc()[-16000:]
        with self.catalog.transaction() as connection:
            connection.execute(
                "UPDATE job SET status=?,progress=?,message=?,result_id=?,error=?,updated_at=? WHERE id=?",
                (
                    status,
                    1 if status == "succeeded" else job["progress"],
                    message,
                    result_id,
                    error,
                    time.time(),
                    identifier,
                ),
            )
