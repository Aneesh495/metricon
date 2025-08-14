import json

import pytest
from fastapi.testclient import TestClient

from conftest import event
from metricon.api.app import Settings, create_app
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.pipeline import import_file
from metricon.models.base import save_model
from metricon.models.baselines import GlobalBaseline
from metricon.storage.artifacts import ArtifactWriter
from metricon.storage.hashing import atomic_json

HEADERS = {"X-Metricon-Client": "1"}


@pytest.fixture
def versioned_workspace(catalog, tmp_path):
    workspace = catalog.create_workspace("Versioned laboratory")
    versions = []
    for index in range(2):
        source = tmp_path / f"source-{index}.ndjson"
        source.write_text(json.dumps(event(index).model_dump(mode="json")))
        versions.append(
            import_file(catalog, workspace["id"], source, AdapterOptions("ndjson", "test"))[
                "dataset_id"
            ]
        )
    other = catalog.create_workspace("Separate workspace")
    source = tmp_path / "other.ndjson"
    source.write_text(json.dumps(event(2).model_dump(mode="json")))
    foreign = import_file(catalog, other["id"], source, AdapterOptions("ndjson", "test"))[
        "dataset_id"
    ]
    return workspace["id"], versions, foreign


@pytest.mark.parametrize("endpoint", ["experiments", "simulations"])
def test_jobs_pin_requested_version_and_reject_foreign_workspace(
    catalog, versioned_workspace, endpoint
):
    workspace, versions, foreign = versioned_workspace
    app = create_app(Settings(catalog.root), start_jobs=False)
    with TestClient(app) as client:
        requested = client.post(
            f"/api/workspaces/{workspace}/{endpoint}?dataset_id={versions[0]}",
            headers=HEADERS,
            json={},
        )
        assert requested.status_code == 202, requested.text
        assert requested.json()["dataset_id"] == versions[0]
        default = client.post(f"/api/workspaces/{workspace}/{endpoint}", headers=HEADERS, json={})
        assert default.status_code == 202
        assert default.json()["dataset_id"] == versions[1]
        rejected = client.post(
            f"/api/workspaces/{workspace}/{endpoint}?dataset_id={foreign}",
            headers=HEADERS,
            json={},
        )
        assert rejected.status_code == 422
        assert len(client.get(f"/api/workspaces/{workspace}/jobs").json()) == 2


@pytest.mark.parametrize("filename,endpoint", [
    ("report.json", "report"),
    ("fold-0/global.model.json", "models/global/parameters"),
])
def test_report_and_parameter_views_reject_corrupted_artifacts(
    catalog, versioned_workspace, filename, endpoint
):
    _, versions, _ = versioned_workspace
    with ArtifactWriter(catalog, "experiment", versions[0]) as writer:
        atomic_json(writer.path / "report.json", {"folds": []})
        save_model(writer.path / "fold-0/global.model.json", GlobalBaseline())
        artifact = writer.publish({"purpose": "Integrity regression"})
    app = create_app(Settings(catalog.root), start_jobs=False)
    with TestClient(app) as client:
        url = f"/api/artifacts/{artifact}/{endpoint}"
        assert client.get(url).status_code == 200
        path = catalog.root / "artifacts" / artifact / filename
        original = path.read_bytes()
        path.write_bytes(original + b"\n ")
        response = client.get(url)
        assert response.status_code == 409
        assert "checksum" in response.json()["detail"].lower()
        path.write_bytes(original)
        assert client.get(url).status_code == 200
