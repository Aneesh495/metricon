from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import numpy as np
from scipy.spatial.distance import jensenshannon

from metricon.evaluation.metrics import inputs


def distribution_shift(
    training: list[dict[str, Any]], evaluation: list[dict[str, Any]]
) -> dict[str, Any]:
    if not training or not evaluation:
        return {"available": False, "reason": "Both populations must be nonempty"}
    result: dict[str, Any] = {
        "available": True,
        "training_n": len(training),
        "evaluation_n": len(evaluation),
    }
    for dimension in ["question_id", "learner_id", "attempt_kind"]:
        train = Counter(row[dimension] for row in training)
        test = Counter(row[dimension] for row in evaluation)
        vocabulary = sorted(set(train) | set(test))
        a = np.array([train.get(key, 0) / len(training) for key in vocabulary])
        b = np.array([test.get(key, 0) / len(evaluation) for key in vocabulary])
        unseen = sum(count for key, count in test.items() if key not in train)
        result[dimension] = {
            "jensen_shannon_distance_base2": float(jensenshannon(a, b, base=2)),
            "training_categories": len(train),
            "evaluation_categories": len(test),
            "unseen_evaluation_rows": unseen,
            "unseen_fraction": unseen / len(evaluation),
        }
    train_skills = {skill for row in training for skill in row["skills"]}
    test_skills = {skill for row in evaluation for skill in row["skills"]}
    result["skills"] = {
        "training_tags": len(train_skills),
        "evaluation_tags": len(test_skills),
        "unseen_tags": sorted(test_skills - train_skills),
        "untagged_training": sum(not row["skills"] for row in training),
        "untagged_evaluation": sum(not row["skills"] for row in evaluation),
    }
    result["class_balance"] = {
        "training": float(np.mean([row["correct"] for row in training])),
        "evaluation": float(np.mean([row["correct"] for row in evaluation])),
    }
    result["interpretation"] = (
        "Descriptive population and item-mix shifts; not a significance test or a causal explanation."
    )
    return result


def residual_diagnostics(
    y: Any, p: Any, learners: list[str], seed: int = 0, repetitions: int = 200
) -> dict[str, Any]:
    outcomes, predictions = inputs(y, p)
    if not len(outcomes):
        return {"available": False, "reason": "No predictions"}
    if len(learners) != len(outcomes):
        raise ValueError("Learner identities must align with residuals")
    residual = outcomes - predictions
    clusters, inverse = np.unique(learners, return_inverse=True)
    cluster_sum = np.bincount(inverse, weights=residual, minlength=len(clusters))
    counts = np.bincount(inverse, minlength=len(clusters))
    interval = None
    if len(clusters) >= 2:
        rng = np.random.default_rng(seed)
        means = []
        for _ in range(repetitions):
            weights = np.bincount(
                rng.integers(0, len(clusters), len(clusters)), minlength=len(clusters)
            )
            means.append(float(weights @ cluster_sum / (weights @ counts)))
        interval = {
            "lower": float(np.quantile(means, 0.025)),
            "upper": float(np.quantile(means, 0.975)),
            "method": "Learner-cluster bootstrap of observed-minus-predicted residual means",
        }
    return {
        "available": True,
        "n": len(outcomes),
        "clusters": len(clusters),
        "mean_observed_minus_predicted": float(residual.mean()),
        "mean_residual_interval": interval,
        "absolute_residual_mean": float(np.abs(residual).mean()),
        "extreme_predictions": {
            "below_01": int(np.sum(predictions < 0.01)),
            "above_99": int(np.sum(predictions > 0.99)),
            "high_confidence_errors": int(
                np.sum(
                    ((predictions > 0.99) & (outcomes == 0))
                    | ((predictions < 0.01) & (outcomes == 1))
                )
            ),
        },
        "interpretation": "Positive mean residual means underprediction. These diagnostics do not refit parameters on test outcomes.",
    }


def sequence_error_profile(rows: list[dict[str, Any]], p: Any, bins: int = 10) -> dict[str, Any]:
    predictions = np.asarray(p, dtype=float)
    if len(rows) != len(predictions):
        raise ValueError("Sequence profile rows do not align with predictions")
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[(row["source_namespace"], row["learner_id"])].append(index)
    assignments = np.zeros(len(rows), dtype=int)
    for indices in groups.values():
        for position, index in enumerate(indices):
            assignments[index] = min(bins - 1, int(position / len(indices) * bins))
    outcomes = np.asarray([int(row["correct"]) for row in rows])
    result = []
    for bucket in range(bins):
        mask = assignments == bucket
        n = int(mask.sum())
        result.append(
            {
                "relative_history_bin": bucket,
                "n": n,
                "observed": float(outcomes[mask].mean()) if n else None,
                "predicted": float(predictions[mask].mean()) if n else None,
                "brier": float(np.mean((outcomes[mask] - predictions[mask]) ** 2)) if n else None,
            }
        )
    return {
        "bins": result,
        "definition": "Within-evaluation relative position; not elapsed time or global chronology",
        "overlapping_bundles": "Split units remain whole; this view does not expose coupled answers to the model",
    }
