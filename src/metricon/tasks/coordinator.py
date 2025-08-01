from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metricon.ingest.pipeline import commit_import
from metricon.schema.events import canonical_json
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json, file_hash
from metricon.storage.lineage import register_experiment_lineage

TERMINAL = {"completed", "failed", "canceled", "interrupted"}


@dataclass
class Running:
    job: dict[str, Any]
    process: subprocess.Popen
    directory: Path
    log: Any
    deadline: float
    offset: int = 0
    cancel_at: float | None = None
    timed_out: bool = False


class JobCoordinator:
    def __init__(self, catalog: Catalog, maximum_workers: int = 2, wall_time_seconds: float = 3600):
        if not 1 <= maximum_workers <= 4 or not 1 <= wall_time_seconds <= 86400:
            raise ValueError("Worker and wall-time bounds are invalid")
        self.catalog = catalog
        self.maximum_workers = maximum_workers
        self.wall_time_seconds = wall_time_seconds
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.thread: threading.Thread | None = None
        self.owner: Any = None
        self.active: dict[str, Running] = {}

    def start(self) -> None:
        path = self.catalog.root / "locks" / "coordinator.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.owner = path.open("a")
        try:
            fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.owner.close()
            raise RuntimeError("This store already has a task coordinator")
        with self.catalog.transaction() as connection:
            connection.execute("UPDATE job SET status='completed' WHERE status='succeeded'")
            connection.execute("UPDATE job SET status='canceled' WHERE status='cancelled'")
            connection.execute(
                "UPDATE job SET status='failed',error='Interrupted coordinator; outputs require reconciliation',updated_at=? WHERE status='running'",
                (time.time(),),
            )
        self.thread = threading.Thread(target=self._loop, name="metricon-coordinator", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.stop_event.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=15)
        if self.thread and self.thread.is_alive():
            raise RuntimeError("Task coordinator did not stop within its shutdown budget")

    def submit(
        self,
        workspace_id: str,
        kind: str,
        parameters: dict[str, Any],
        dataset_id: str | None = None,
    ) -> dict[str, Any]:
        if kind not in {"import", "experiment", "analytics", "simulation"}:
            raise ValueError("Unknown task kind")
        budget = parameters.get("wall_time_seconds", self.wall_time_seconds)
        if not isinstance(budget, (int, float)) or not 1 <= budget <= 86400:
            raise ValueError("Task wall-time budget must be between 1 and 86400 seconds")
        workspace = self.catalog.workspace(workspace_id)
        dataset = dataset_id or workspace["dataset_id"]
        if kind != "import" and dataset is None:
            raise ValueError("Import a dataset before submitting analytical tasks")
        if dataset and self.catalog.dataset(dataset)["workspace_id"] != workspace_id:
            raise ValueError("Dataset does not belong to workspace")
        identifier, now = uuid.uuid4().hex, time.time()
        with self.catalog.transaction() as connection:
            connection.execute(
                "INSERT INTO job(id,workspace_id,dataset_id,kind,parameters,status,created_at,updated_at) VALUES (?,?,?,?,?,'queued',?,?)",
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
            raise KeyError("Task does not exist")
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
                raise KeyError("Task does not exist")
            if row["status"] not in TERMINAL:
                connection.execute(
                    "UPDATE job SET cancel_requested=1,status=?,message=?,updated_at=? WHERE id=?",
                    (
                        "canceled" if row["status"] == "queued" else row["status"],
                        "Cancellation requested",
                        time.time(),
                        identifier,
                    ),
                )
        self.wake.set()
        return self.get(identifier)

    def _claim(self) -> dict[str, Any] | None:
        occupied = {
            item.job["workspace_id"]
            for item in self.active.values()
            if item.job["kind"] == "import"
        }
        with self.catalog.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM job WHERE status='queued' AND cancel_requested=0 ORDER BY created_at LIMIT 100"
            ).fetchall()
            row = next(
                (
                    row
                    for row in rows
                    if row["kind"] != "import" or row["workspace_id"] not in occupied
                ),
                None,
            )
            if row is None:
                return None
            connection.execute(
                "UPDATE job SET status='running',updated_at=? WHERE id=?", (time.time(), row["id"])
            )
        return self.get(row["id"])

    def _launch(self, job: dict[str, Any]) -> None:
        directory = self.catalog.root / "task-runtime" / job["id"]
        directory.mkdir(parents=True)
        request = directory / "request.json"
        atomic_json(request, {"job": job, "owner_pid": os.getpid()})
        log = (directory / "worker.log").open("wb")
        environment = {
            **os.environ,
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "POLARS_MAX_THREADS": "2",
        }
        process = subprocess.Popen(
            [sys.executable, "-m", "metricon.tasks.worker", str(self.catalog.root), str(request)],
            stdout=log,
            stderr=log,
            env=environment,
            start_new_session=True,
        )
        self.active[job["id"]] = Running(
            job,
            process,
            directory,
            log,
            time.monotonic() + job["parameters"].get("wall_time_seconds", self.wall_time_seconds),
        )
        atomic_json(
            directory / "process.json",
            {
                "pid": process.pid,
                "started_at": time.time(),
                "ownership": "Dedicated task process group",
            },
        )

    def _progress(self, identifier: str, running: Running) -> None:
        path = running.directory / "progress.ndjson"
        if not path.exists():
            return
        with path.open() as handle:
            handle.seek(running.offset)
            lines = []
            while line := handle.readline():
                if not line.endswith("\n"):
                    break
                lines.append(line)
                running.offset = handle.tell()
        if lines:
            result = json.loads(lines[-1])
            with self.catalog.transaction() as connection:
                connection.execute(
                    "UPDATE job SET progress=?,message=?,updated_at=? WHERE id=?",
                    (
                        min(0.99, max(0, result["progress"])),
                        result["message"][:2000],
                        time.time(),
                        identifier,
                    ),
                )

    def _finish(self, identifier: str, running: Running) -> None:
        running.log.close()
        result_path = running.directory / "result.json"
        response = (
            json.loads(result_path.read_text())
            if result_path.exists()
            else {
                "success": False,
                "message": f"Worker exited {running.process.returncode} without a complete result",
                "error": (running.directory / "worker.log").read_text(errors="replace")[-16000:],
            }
        )
        status, result_id = "failed", None
        if running.cancel_at is not None:
            status = "failed" if running.timed_out else "canceled"
            response["message"] = (
                "Wall-time budget exceeded"
                if running.timed_out
                else "Task canceled before coordinator publication"
            )
        elif response["success"]:
            try:
                for request in response["publications"]:
                    if request["operation"] == "import":
                        commit_import(self.catalog, request)
                    elif request["operation"] == "artifact":
                        directory = self.catalog.root / "artifacts" / request["identifier"]
                        if any(
                            file_hash(directory / name) != expected
                            for name, expected in request["manifest"]["files"].items()
                        ):
                            raise RuntimeError("Worker artifact checksum verification failed")
                        self.catalog.record_artifact(
                            request["identifier"],
                            request["kind"],
                            request["dataset_id"],
                            request["manifest"],
                            request["parents"],
                        )
                        if request["kind"] == "experiment":
                            register_experiment_lineage(self.catalog, request["identifier"])
                result_id, status = response["result_id"], "completed"
            except Exception:
                response["error"] = traceback.format_exc()
                response["message"] = "Coordinator publication failed"
        progress = self.get(identifier)["progress"]
        with self.catalog.transaction() as connection:
            connection.execute(
                "UPDATE job SET status=?,progress=?,message=?,result_id=?,error=?,updated_at=? WHERE id=?",
                (
                    status,
                    1 if status == "completed" else progress,
                    response["message"][:2000],
                    result_id,
                    response.get("error"),
                    time.time(),
                    identifier,
                ),
            )
        del self.active[identifier]

    def _loop(self) -> None:
        try:
            while not self.stop_event.is_set() or self.active:
                for identifier, running in list(self.active.items()):
                    self._progress(identifier, running)
                    now = time.monotonic()
                    requested = self.stop_event.is_set() or self.get(identifier)["cancel_requested"]
                    if now > running.deadline:
                        requested, running.timed_out = True, True
                    if requested and running.cancel_at is None:
                        (running.directory / "cancel").touch()
                        running.cancel_at = now
                    if (
                        running.cancel_at
                        and now - running.cancel_at > 5
                        and running.process.poll() is None
                    ):
                        os.killpg(running.process.pid, signal.SIGKILL)
                    if running.process.poll() is not None:
                        self._finish(identifier, running)
                while not self.stop_event.is_set() and len(self.active) < self.maximum_workers:
                    job = self._claim()
                    if job is None:
                        break
                    self._launch(job)
                self.wake.wait(0.1)
                self.wake.clear()
        finally:
            for running in self.active.values():
                if running.process.poll() is None:
                    os.killpg(running.process.pid, signal.SIGKILL)
                    running.process.wait(timeout=3)
                running.log.close()
            if self.owner and not self.owner.closed:
                fcntl.flock(self.owner, fcntl.LOCK_UN)
                self.owner.close()
