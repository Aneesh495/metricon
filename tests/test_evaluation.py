import numpy as np
import pytest

from metricon.evaluation.calibration import PlattCalibrator
from metricon.evaluation.metrics import cluster_intervals, metric_summary, paired_comparison
from metricon.evaluation.splits import forward_split, learner_split, rolling_splits, audit_split
from metricon.evaluation.experiment import ExperimentConfig, run_experiment
from metricon.ingest.demo import demo_workspace
from metricon.storage.artifacts import verify_artifact
from metricon.storage.hashing import read_json


def test_splits_no_session_or_learner_leakage(rows):
    for split in [forward_split(rows), learner_split(rows), *rolling_splits(rows)]:
        assert audit_split(rows, split)["valid"]
        assignments = {}
        for row in rows:
            key = (row["learner_id"], row["session_id"])
            assignments.setdefault(key, set()).add(split.assignments[row["identity"]])
        assert all(len(partitions) == 1 for partitions in assignments.values())


def test_metrics_unknown_and_extreme():
    assert metric_summary([], [])["log_loss"] is None
    assert metric_summary([1, 1], [0.99, 0.01])["auroc"] is None
    result = metric_summary([0, 1], [0, 1])
    assert result["brier"] < 1e-12
    assert result["auroc"] == 1
    assert result["calibration"]["bins"][3]["observed"]["estimate"] is None
    with pytest.raises(ValueError):
        metric_summary([0, 1], [np.nan, 0.2])


def test_cluster_bootstrap_preserves_clusters_and_pairing():
    y = [0, 1, 0, 1]
    p = [0.2, 0.8, 0.3, 0.7]
    clusters = ["a", "a", "b", "b"]
    a = cluster_intervals(y, p, clusters, 20, 13)
    assert a == cluster_intervals(y, p, clusters, 20, 13)
    result = paired_comparison(y, p, p, clusters, 20)
    assert result["lower"] == result["upper"] == 0
    assert not cluster_intervals(y, p, ["a"] * 4, 20)["available"]


def test_calibration_requires_validation_support():
    calibrator = PlattCalibrator().fit([1, 0], [0.9, 0.2])
    assert not calibrator.diagnostics["fitted"]
    np.testing.assert_allclose(calibrator.predict([0.2, 0.8]), [0.2, 0.8])


def test_reusable_pipeline_hashes_every_artifact(catalog):
    demo = demo_workspace(catalog, learners=5, attempts=30)
    dataset = demo["workspace"]["dataset_id"]
    artifact = run_experiment(
        catalog,
        dataset,
        ExperimentConfig(
            families=("global", "item_prior", "recent"), bootstrap_repetitions=20, ablations=False
        ),
    )
    assert verify_artifact(catalog, artifact)["valid"]
    report = read_json(catalog.root / "artifacts" / artifact / "report.json")
    assert report["folds"][0]["models"]["global"]["test"]["n"] > 0
    assert catalog.ancestors(artifact)
