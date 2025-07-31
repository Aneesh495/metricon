import time

from fastapi.testclient import TestClient

from metricon.api.app import Settings, create_app
from metricon.ingest.demo import demo_workspace
from metricon.recommendation.planner import PlannerConfig, plan
from metricon.simulation.engine import SimulationConfig, simulate

HEADERS = {"X-Metricon-Client": "1"}


def test_api_empty_import_job_and_artifact_contract(tmp_path):
    app = create_app(Settings(tmp_path / "api-root"))
    with TestClient(app) as client:
        assert client.get("/api/workspaces").json() == []
        assert client.post("/api/workspaces", json={"name": "blank"}).status_code == 403
        workspace = client.post("/api/workspaces", headers=HEADERS, json={"name": "blank"}).json()
        assert workspace["dataset_id"] is None
        payload = b'{"q1":{"attempts":[{"id":"a","correct":false},{"id":"b","correct":true}]}}'
        upload = client.post(
            "/api/uploads", headers=HEADERS, files={"file": ("legacy.json", payload)}
        ).json()
        options = {"format": "legacy", "namespace": "browser", "learner": "local"}
        preview = client.post(
            f"/api/uploads/{upload['upload_id']}/preview", headers=HEADERS, json=options
        )
        assert preview.status_code == 200
        assert preview.json()["events"][0]["timestamp"] is None
        job = client.post(
            f"/api/workspaces/{workspace['id']}/import",
            headers=HEADERS,
            json={"upload_id": upload["upload_id"], "options": options},
        ).json()
        for _ in range(100):
            result = client.get(f"/api/jobs/{job['id']}").json()
            if result["status"] in {"completed", "failed"}:
                break
            time.sleep(0.02)
        assert result["status"] == "completed", result
        dataset = result["result_id"]
        overview = client.get(f"/api/datasets/{dataset}/overview").json()
        assert overview["accuracy"]["n"] == 2
        assert overview["accuracy"]["estimate"] == 0.5
        trend = client.get(f"/api/datasets/{dataset}/trend?learner_id=local").json()
        assert trend["available"]
        assert client.get("/api/docs").status_code == 200
        assert client.get("/api/health", headers={"Host": "malicious.example"}).status_code == 400
        invalid = client.get("/api/artifacts/not-real/files/../../catalog.sqlite")
        assert invalid.status_code != 200


def test_timestamped_group_api(catalog):
    demo = demo_workspace(catalog, learners=2, attempts=10)
    app = create_app(Settings(catalog.root), start_jobs=False)
    with TestClient(app) as client:
        response = client.get(
            f"/api/datasets/{demo['workspace']['dataset_id']}/groups?dimension=learner"
        )
        assert response.status_code == 200
        assert response.json()["rows"][0]["first_timestamp"] is not None
        dataset = demo["workspace"]["dataset_id"]
        for endpoint in ["streaks", "sessions", "drift", "history", "cohort"]:
            response = client.get(f"/api/datasets/{dataset}/{endpoint}?learner_id=demo-000")
            assert response.status_code == 200, (endpoint, response.text)
        streak = client.get(f"/api/datasets/{dataset}/streaks?learner_id=demo-000").json()
        assert streak["domains"]
        assert streak["domains"][0]["longest_correct_streak"] > 0


def test_planner_unknown_time_not_imputed(catalog):
    result = demo_workspace(catalog, learners=2, attempts=90)
    dataset = result["workspace"]["dataset_id"]
    planned = plan(catalog, dataset, "demo-000", PlannerConfig(budget_seconds=900))
    assert planned["planned_seconds"] <= 900
    assert all(action["duration"]["n"] >= 3 for action in planned["actions"])
    assert all(action["planned_seconds"] > 0 for action in planned["actions"])
    assert planned["unknown_time_actions"] == []


def test_prerequisite_cycle_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        PlannerConfig(prerequisites={"a": ["b"], "b": ["a"]}).validate()


def test_simulation_reproducible_and_explicit():
    configuration = SimulationConfig(repetitions=20, max_actions=100)
    first = simulate(configuration)
    assert first == simulate(configuration)
    assert first["synthetic"] is True
    assert all(row["actions"]["mean"] <= 15 for row in first["summaries"].values())
    for trajectory in first["trajectories"]:
        assert all(row["elapsed_seconds"] <= 900 for row in trajectory["events"])
