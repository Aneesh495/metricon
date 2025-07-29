from __future__ import annotations

import json
from typing import Any

import duckdb
import numpy as np

from metricon.evaluation.metrics import metric_summary
from metricon.storage.artifacts import verify_artifact
from metricon.storage.catalog import Catalog


def evaluate_frozen(catalog: Catalog, identifier: str) -> dict[str, Any]:
    artifact = catalog.artifact(identifier)
    if artifact["kind"] != "experiment" or not verify_artifact(catalog, identifier)["valid"]:
        raise ValueError("Frozen evaluation requires a complete verified experiment")
    root = catalog.root / "artifacts" / identifier
    report = json.loads((root / "report.json").read_text())
    results = []
    with duckdb.connect(":memory:") as connection:
        for fold_index, fold in enumerate(report["folds"]):
            path = root / f"fold-{fold_index}" / "predictions.parquet"
            for name, model in fold["models"].items():
                if not model["eligible"]:
                    continue
                rows = connection.execute(
                    "SELECT correct,probability,calibrated_probability FROM read_parquet(?) WHERE model=? AND partition='test' ORDER BY identity",
                    [str(path), name],
                ).fetchall()
                actual = metric_summary([row[0] for row in rows], [row[1] for row in rows])
                for key in ["n", "positives", "log_loss", "brier", "auroc"]:
                    expected = model["test"][key]
                    if expected is None:
                        if actual[key] is not None:
                            raise ValueError("Frozen metric eligibility changed")
                    elif not np.isclose(expected, actual[key], atol=1e-12, rtol=1e-12):
                        raise ValueError(f"Frozen predictions do not reproduce {name}/{key}")
                if model.get("calibrated_test") and rows:
                    calibrated = metric_summary([row[0] for row in rows], [row[2] for row in rows])
                    if not np.isclose(
                        calibrated["log_loss"], model["calibrated_test"]["log_loss"], atol=1e-12
                    ):
                        raise ValueError("Frozen calibrated predictions differ from report")
                results.append({"fold": fold_index, "model": name, "metrics": actual})
    return {
        "artifact_id": identifier,
        "dataset_id": artifact["dataset_id"],
        "valid": True,
        "results": results,
        "method": "Recompute metrics from hashed frozen test predictions without refitting",
    }
