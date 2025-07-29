from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.stats import fisher_exact

from metricon.analytics.statistics import wilson
from metricon.schema.events import digest
from metricon.storage.catalog import Catalog
from metricon.storage.query import analytical_connection


@dataclass(frozen=True)
class DriftConfig:
    window_events: int = 100
    minimum_events: int = 50
    response_effect: float = 0.1
    missingness_effect: float = 0.1
    item_coverage_effect: float = 0.25
    seed: int = 2026

    def validate(self) -> None:
        if not 30 <= self.minimum_events <= self.window_events <= 10000:
            raise ValueError("Drift windows require 30 or more observations and bounded size")
        if any(
            not 0 < value < 1
            for value in [self.response_effect, self.missingness_effect, self.item_coverage_effect]
        ):
            raise ValueError("Drift effect thresholds must be probabilities")


def window_diagnostics(
    reference: list[dict[str, Any]], current: list[dict[str, Any]], config: DriftConfig
) -> dict[str, Any]:
    config.validate()
    if min(len(reference), len(current)) < config.minimum_events:
        return {
            "available": False,
            "reason": "Insufficient eligible observations in one or both actual windows",
            "reference_n": len(reference),
            "current_n": len(current),
            "minimum_events": config.minimum_events,
        }
    n0, n1 = len(reference), len(current)
    s0, s1 = sum(row["correct"] for row in reference), sum(row["correct"] for row in current)
    difference = s1 / n1 - s0 / n0
    p_value = float(fisher_exact([[s0, n0 - s0], [s1, n1 - s1]]).pvalue)
    rng = np.random.default_rng(config.seed)
    draws = rng.beta(s1 + 1, n1 - s1 + 1, 10000) - rng.beta(s0 + 1, n0 - s0 + 1, 10000)
    interval = np.quantile(draws, [0.025, 0.975]).tolist()
    missingness = {}
    for field in ["timestamp", "duration_ms", "session_id"]:
        m0 = sum(row.get(field) is None for row in reference)
        m1 = sum(row.get(field) is None for row in current)
        missingness[field] = {
            "reference": wilson(m0, n0),
            "current": wilson(m1, n1),
            "difference": m1 / n1 - m0 / n0,
            "alert": abs(m1 / n1 - m0 / n0) >= config.missingness_effect,
        }
    items0 = Counter(row["question_id"] for row in reference)
    unseen = sum(row["question_id"] not in items0 for row in current)
    coverage = {
        "reference_items": len(items0),
        "current_items": len({row["question_id"] for row in current}),
        "current_unseen": wilson(unseen, n1),
        "alert": unseen / n1 >= config.item_coverage_effect,
    }
    probabilities_available = all(row.get("prediction") is not None for row in reference + current)
    calibration = None
    if probabilities_available:
        from metricon.evaluation.metrics import calibration_curve

        calibration = {
            "reference": calibration_curve(
                np.array([row["correct"] for row in reference]),
                np.array([row["prediction"] for row in reference]),
            ),
            "current": calibration_curve(
                np.array([row["correct"] for row in current]),
                np.array([row["prediction"] for row in current]),
            ),
        }
    return {
        "available": True,
        "reference_n": n0,
        "current_n": n1,
        "response": {
            "reference": wilson(s0, n0),
            "current": wilson(s1, n1),
            "difference": difference,
            "difference_interval": interval,
            "p_value": p_value,
            "alert": abs(difference) >= config.response_effect
            and (interval[0] > 0 or interval[1] < 0),
        },
        "missingness": missingness,
        "item_coverage": coverage,
        "calibration": calibration,
        "assumptions": "Response interval treats window observations as independent; repeated answers may be dependent. Alerts are descriptive diagnostics and require human inspection, not automatic refitting.",
    }


def drift_report(
    catalog: Catalog,
    dataset_id: str,
    learner_id: str,
    config: DriftConfig = DriftConfig(),
    artifact_id: str | None = None,
    model: str = "bkt",
) -> dict[str, Any]:
    config.validate()
    with analytical_connection(catalog, dataset_id) as connection:
        domains = connection.execute(
            "SELECT DISTINCT source_namespace,CASE WHEN order_scope='question' THEN question_id ELSE '' END FROM events WHERE learner_id=?",
            [learner_id],
        ).fetchall()
        if len(domains) != 1:
            return {
                "available": False,
                "reason": "Drift requires one known learner order domain; no global chronology is inferred",
            }
        reader = connection.execute(
            "SELECT * FROM events WHERE learner_id=? ORDER BY timestamp DESC NULLS LAST,source_sequence DESC,event_id DESC LIMIT ?",
            [learner_id, config.window_events * 2],
        ).fetch_arrow_table()
    rows = list(reversed(reader.to_pylist()))
    current = rows[-config.window_events :]
    reference = rows[: -config.window_events]
    if artifact_id:
        artifact = catalog.artifact(artifact_id)
        if artifact["dataset_id"] != dataset_id or artifact["kind"] != "experiment":
            raise ValueError(
                "Drift calibration requires a fitted run on this exact dataset version"
            )
        import duckdb

        predictions = catalog.root / "artifacts" / artifact_id / "fold-0/predictions.parquet"
        with duckdb.connect(":memory:") as connection:
            probability_rows = connection.execute(
                "SELECT identity,probability FROM read_parquet(?) WHERE model=? AND partition='test' AND learner_id=?",
                [str(predictions), model, learner_id],
            ).fetchall()
        lookup = dict(probability_rows)
        for row in rows:
            row["prediction"] = lookup.get(row["identity"])
    result = window_diagnostics(reference, current, config)
    result.update(
        {
            "dataset_id": dataset_id,
            "learner_id": learner_id,
            "artifact_id": artifact_id,
            "window_hash": digest([dataset_id, [row["identity"] for row in rows], vars(config)]),
            "configuration": vars(config),
            "window_axis": "Adjacent source/learner event-order windows, not calendar dates",
            "reference_identities": [row["identity"] for row in reference],
            "current_identities": [row["identity"] for row in current],
            "refit_performed": False,
        }
    )
    return result
