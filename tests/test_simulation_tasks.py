import json
import time

import pytest

from metricon.ingest.demo import demo_workspace
from metricon.simulation.engine import SimulationConfig, simulate
from metricon.tasks.coordinator import JobCoordinator


def test_progress_preserves_seeded_outcomes_and_reports_completed_trials():
    config = SimulationConfig(repetitions=3, retain_all_trajectories=True)
    completed = []
    observed = simulate(config, progress=lambda value, message: completed.append((value, message)))
    assert observed == simulate(config)
    assert len(completed) == len(observed["outcomes"])
    assert completed[0][0] > 0
    assert completed[-1] == (1, "Completed 15 of 15 policy trials")
    assert all(left[0] < right[0] for left, right in zip(completed, completed[1:]))


def test_cancellation_interrupts_a_long_trial_before_its_outcome():
    checks = 0
    progress = []

    def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 8

    with pytest.raises(RuntimeError, match="Cooperative task cancellation"):
        simulate(
            SimulationConfig(repetitions=5000, budget_seconds=60000, max_actions=1000),
            progress=lambda *record: progress.append(record),
            cancelled=cancelled,
        )
    assert progress == []
    assert checks < 12


def test_running_simulation_cancels_cooperatively_without_publication(catalog):
    demo = demo_workspace(catalog, learners=2, attempts=20)
    coordinator = JobCoordinator(catalog, maximum_workers=1, wall_time_seconds=30)
    job = coordinator.submit(
        demo["workspace"]["id"],
        "simulation",
        {
            "repetitions": 5000,
            "budget_seconds": 60000,
            "max_actions": 1000,
            "skills": [f"skill-{index}" for index in range(100)],
        },
    )
    directory = catalog.root / "task-runtime" / job["id"]
    coordinator.start()
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            progress = directory / "progress.ndjson"
            if progress.is_file() and progress.stat().st_size:
                break
            time.sleep(0.05)
        assert progress.is_file() and progress.stat().st_size
        assert coordinator.get(job["id"])["status"] == "running"
        coordinator.cancel(job["id"])
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = coordinator.get(job["id"])
            if state["status"] in {"completed", "failed", "canceled"}:
                break
            time.sleep(0.05)
        assert state["status"] == "canceled", state
        response = json.loads((directory / "result.json").read_text())
        assert response["success"] is False
        assert response["message"] == "Cooperative task cancellation"
        assert response["publications"] == []
        assert state["result_id"] is None
        assert catalog.artifacts(demo["workspace"]["dataset_id"], "simulation") == []
    finally:
        coordinator.close()
