import pytest

from metricon.evaluation.diagnostics import distribution_shift, residual_diagnostics
from metricon.storage.lineage import LineageGraph
from metricon.models.cohort import CohortRestrictions, eligible_cohort
from metricon.models.trace import replay_bkt
from metricon.evaluation.predictions import PredictionInspector
from metricon.evaluation.experiment import ExperimentConfig, run_experiment
from metricon.ingest.demo import demo_workspace


def test_lineage_prevents_cycles(catalog):
    graph = LineageGraph(catalog)
    graph.register("a", "source", {})
    graph.register("b", "features", {}, parents={"source": "a"})
    with pytest.raises(ValueError):
        graph.register("a", "source", {}, parents={"future": "b"})
    assert graph.descendants("a") == ["b"]
    assert graph.graph("b")["levels"] == [["a"], ["b"]]


def test_distribution_shift_and_residuals(rows):
    shift = distribution_shift(rows[:100], rows[-100:])
    assert shift["learner_id"]["unseen_fraction"] == 1
    result = residual_diagnostics(
        [0, 1, 0, 1], [0.2, 0.8, 0.2, 0.8], ["a", "a", "b", "b"], repetitions=20
    )
    assert abs(result["mean_observed_minus_predicted"]) < 1e-12
    assert result["clusters"] == 2


def test_irt_connected_cohort(rows):
    selected, report = eligible_cohort(rows, CohortRestrictions(minimum_item_responses=5))
    assert report["eligible"]
    assert report["retained_rows"] == len(selected)
    assert report["connected_components_before_restriction"] == 1


def test_saved_prediction_inspection_and_replay(catalog):
    demonstration = demo_workspace(catalog, learners=5, attempts=30)
    artifact = run_experiment(
        catalog,
        demonstration["workspace"]["dataset_id"],
        ExperimentConfig(
            families=("global", "bkt"),
            bootstrap_repetitions=20,
            bkt_starts=1,
            bkt_max_iterations=10,
            ablations=False,
        ),
    )
    inspector = PredictionInspector(catalog, artifact)
    page = inspector.rows("global", limit=3)
    assert len(page["rows"]) == 3
    assert inspector.slice("global")["metrics"]["n"] == page["total"]
    replay = replay_bkt(catalog, artifact, "bkt", "demo-000", limit=3)
    assert len(replay["rows"]) == 3 and replay["total"] == 30
    assert all(row["unit"] == 0 for row in replay["rows"])
    for row in replay["rows"]:
        for skill in row["skills_before_unit"]:
            assert skill["prior_knowledge"] == skill["parameters"]["initial"]
    graph = LineageGraph(catalog)
    assert graph.verify(artifact)["valid"]
    kinds = {node["kind"] for node in graph.graph(artifact)["nodes"]}
    assert {"feature-contract", "pipeline-source", "fitted-model", "held-out-predictions"}.issubset(
        kinds
    )
