from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from metricon.evaluation.metrics import paired_comparison
from metricon.storage.artifacts import verify_artifact
from metricon.storage.catalog import Catalog


def read_prediction_rows(
    root: Path, artifact: str, model: str, fold: int = 0
) -> list[dict[str, Any]]:
    path = root / "artifacts" / artifact / f"fold-{fold}" / "predictions.parquet"
    with duckdb.connect(":memory:") as connection:
        return (
            connection.execute(
                "SELECT identity,learner_id,correct,probability FROM read_parquet(?) WHERE model=? AND partition='test' ORDER BY identity",
                [str(path), model],
            )
            .fetch_arrow_table()
            .to_pylist()
        )


def compare_runs(
    catalog: Catalog,
    left: str,
    right: str,
    left_model: str = "bkt",
    right_model: str = "global",
    fold: int = 0,
    seed: int = 2026,
    repetitions: int = 200,
) -> dict[str, Any]:
    runs = []
    for identifier, model in [(left, left_model), (right, right_model)]:
        artifact = catalog.artifact(identifier)
        if artifact["kind"] != "experiment" or not verify_artifact(catalog, identifier)["valid"]:
            raise ValueError("Comparison requires complete verified experiment artifacts")
        report = json.loads((catalog.root / "artifacts" / identifier / "report.json").read_text())
        if not 0 <= fold < len(report["folds"]):
            raise ValueError("Comparison fold is absent from one run")
        result = report["folds"][fold]["models"].get(model)
        if result is None or not result["eligible"]:
            raise ValueError("Comparison model is unavailable in one run")
        runs.append(
            {
                "artifact_id": identifier,
                "dataset_id": artifact["dataset_id"],
                "model": model,
                "split_hash": report["folds"][fold]["split_hash"],
                "configuration": report["configuration"],
                "test": result["test"],
                "calibrated_test": result.get("calibrated_test"),
                "intervals": result.get("intervals"),
                "source_hash": report["source_code"]["hash"],
            }
        )
    identical_dataset = runs[0]["dataset_id"] == runs[1]["dataset_id"]
    identical_split = runs[0]["split_hash"] == runs[1]["split_hash"]
    paired = None
    if identical_dataset and identical_split:
        a = read_prediction_rows(catalog.root, left, left_model, fold)
        b = read_prediction_rows(catalog.root, right, right_model, fold)
        if [(row["identity"], row["correct"], row["learner_id"]) for row in a] != [
            (row["identity"], row["correct"], row["learner_id"]) for row in b
        ]:
            raise ValueError("Nominally identical splits contain different target rows")
        paired = paired_comparison(
            [row["correct"] for row in a],
            [row["probability"] for row in a],
            [row["probability"] for row in b],
            [row["learner_id"] for row in a],
            repetitions,
            seed,
        )
    return {
        "left": runs[0],
        "right": runs[1],
        "paired": paired,
        "same_dataset": identical_dataset,
        "same_split": identical_split,
        "interpretation": "Paired learner resampling on identical test targets"
        if paired
        else "Descriptive comparison of different populations or splits; metric differences are not evidence that one model improves the other population",
        "selection": "This comparison does not refit, recalibrate, or select parameters using test outcomes",
    }
