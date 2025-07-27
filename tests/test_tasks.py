import json
import time

import pytest

from conftest import event
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.demo import demo_workspace
from metricon.ingest.pipeline import commit_import, import_file
from metricon.storage.catalog import Catalog
from metricon.tasks.coordinator import JobCoordinator


def test_worker_metadata_is_read_only_and_publication_deferred(catalog, tmp_path):
    workspace = catalog.create_workspace("empty")
    source = tmp_path / "canonical.ndjson"
    source.write_text(json.dumps(event().model_dump(mode="json", exclude={"provenance"})) + "\n")
    worker = Catalog(catalog.root, read_only=True)
    with pytest.raises(RuntimeError, match="cannot mutate"):
        with worker.transaction():
            pass
    result = import_file(worker, workspace["id"], source, AdapterOptions("ndjson", "test"))
    assert catalog.workspace(workspace["id"])["dataset_id"] is None
    assert len(worker.deferred_publications) == 1
    commit_import(catalog, worker.deferred_publications[0])
    assert catalog.workspace(workspace["id"])["dataset_id"] == result["dataset_id"]


def test_process_cancellation_and_wall_time(catalog):
    demo = demo_workspace(catalog, learners=2, attempts=20)
    workspace = demo["workspace"]["id"]
    coordinator = JobCoordinator(catalog, maximum_workers=1, wall_time_seconds=1)
    queued = coordinator.submit(
        workspace, "simulation", {"repetitions": 5000, "max_actions": 1000, "budget_seconds": 60000}
    )
    canceled = coordinator.submit(workspace, "analytics", {})
    assert coordinator.cancel(canceled["id"])["status"] == "canceled"
    coordinator.start()
    try:
        for _ in range(150):
            task = coordinator.get(queued["id"])
            if task["status"] in {"completed", "failed", "canceled"}:
                break
            time.sleep(0.1)
        assert task["status"] == "failed", task
        assert "Wall-time" in task["message"]
        assert task["result_id"] is None
        assert catalog.artifacts(demo["workspace"]["dataset_id"], "simulation") == []
    finally:
        coordinator.close()
