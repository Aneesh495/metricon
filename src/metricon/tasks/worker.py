from __future__ import annotations

import json
import os
import threading
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from metricon.analytics.engine import Analytics
from metricon.evaluation.experiment import ExperimentConfig, run_experiment
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.pipeline import import_file
from metricon.simulation.engine import SimulationConfig, simulate
from metricon.storage.artifacts import ArtifactWriter
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json, file_hash


def execute(root: Path, request_path: Path) -> None:
    request = json.loads(request_path.read_text())
    owner_pid = request.get("owner_pid", os.getppid())

    def watch_parent() -> None:
        while True:
            if os.getppid() != owner_pid:
                os._exit(72)
            time.sleep(0.5)

    threading.Thread(target=watch_parent, daemon=True).start()
    directory = request_path.parent
    catalog = Catalog(root, read_only=True)
    job = request["job"]
    parameters = dict(job["parameters"])
    parameters.pop("wall_time_seconds", None)
    started = time.monotonic()

    def cancelled() -> bool:
        return (directory / "cancel").exists()

    def progress(value: float, message: str) -> None:
        with (directory / "progress.ndjson").open("a") as handle:
            handle.write(json.dumps({"progress": value, "message": message}) + "\n")
        if cancelled():
            raise RuntimeError("Cooperative task cancellation")

    try:
        if job["kind"] == "import":
            upload = root / "uploads" / parameters["upload_id"]
            if not upload.is_file() or file_hash(upload) != parameters["upload_id"]:
                raise ValueError("Uploaded source checksum changed")
            result = import_file(
                catalog,
                job["workspace_id"],
                upload,
                AdapterOptions(**parameters["options"]),
                progress=lambda count: progress(0, f"Processed {count} records"),
                cancelled=cancelled,
            )
            result_id = result["dataset_id"]
            message = json.dumps(result, ensure_ascii=False)
        elif job["kind"] == "experiment":
            result_id = run_experiment(
                catalog, job["dataset_id"], ExperimentConfig(**parameters), progress, cancelled
            )
            message = "Experiment outputs complete"
        elif job["kind"] == "analytics":
            result_id = Analytics(catalog, job["dataset_id"]).materialize(parameters)
            message = "Analytical outputs complete"
        else:
            result = simulate(SimulationConfig(**parameters))
            progress(0.9, "Simulation trajectories complete")
            with ArtifactWriter(catalog, "simulation", job["dataset_id"]) as writer:
                atomic_json(writer.path / "simulation.json", result)
                result_id = writer.publish({"configuration": parameters, "synthetic": True})
            message = "Simulation outputs complete"
        progress(0.99, "Awaiting coordinator publication")
        response: dict[str, Any] = {
            "success": True,
            "result_id": result_id,
            "message": message,
            "publications": catalog.deferred_publications,
        }
    except Exception as error:
        response = {
            "success": False,
            "message": str(error),
            "error": traceback.format_exc(),
            "publications": [],
        }
    response["worker_seconds"] = time.monotonic() - started
    atomic_json(directory / "result.json", response)


if __name__ == "__main__":
    execute(Path(sys.argv[1]), Path(sys.argv[2]))
