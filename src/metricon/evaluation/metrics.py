from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score

from metricon.analytics.statistics import wilson
from metricon.models.base import probabilities


def inputs(y: Any, p: Any) -> tuple[np.ndarray, np.ndarray]:
    outcomes = np.asarray(y)
    predictions = np.asarray(p, dtype=float)
    if outcomes.ndim != 1 or predictions.ndim != 1 or outcomes.shape != predictions.shape:
        raise ValueError("Labels and predictions must be aligned one-dimensional arrays")
    if not np.all(np.isin(outcomes, [0, 1])):
        raise ValueError("Labels must be binary")
    if not np.all(np.isfinite(predictions)) or np.any(predictions < 0) or np.any(predictions > 1):
        raise ValueError("Probabilities must be finite and in [0,1]")
    return outcomes.astype(np.int8), probabilities(predictions)


def calibration_curve(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict[str, Any]:
    y, p = inputs(y, p)
    if not 2 <= bins <= 100:
        raise ValueError("Calibration bins must be 2..100")
    index = np.minimum((p * bins).astype(int), bins - 1)
    rows = []
    error = 0.0
    for bucket in range(bins):
        mask = index == bucket
        n = int(mask.sum())
        successes = int(y[mask].sum())
        mean_prediction = float(p[mask].mean()) if n else None
        mean_observed = successes / n if n else None
        if n:
            error += n * abs(mean_prediction - mean_observed)
        rows.append(
            {
                "bin": bucket,
                "left": bucket / bins,
                "right": (bucket + 1) / bins,
                "n": n,
                "prediction": mean_prediction,
                "observed": wilson(successes, n),
            }
        )
    return {
        "bins": rows,
        "ece": error / len(y) if len(y) else None,
        "method": "Equal-width bins; ECE is weighted absolute observed-minus-predicted gap",
        "empty_bins": "unknown",
        "bin_count": bins,
    }


def metric_summary(y: Any, p: Any, bins: int = 10) -> dict[str, Any]:
    outcomes, predictions = inputs(y, p)
    n = len(outcomes)
    if n == 0:
        return {
            "n": 0,
            "positives": 0,
            "class_balance": None,
            "log_loss": None,
            "brier": None,
            "auroc": None,
            "accuracy": wilson(0, 0),
            "calibration": calibration_curve(outcomes, predictions, bins),
        }
    losses = -(outcomes * np.log(predictions) + (1 - outcomes) * np.log1p(-predictions))
    correct = int(np.sum((predictions >= 0.5) == outcomes))
    auroc = float(roc_auc_score(outcomes, predictions)) if len(np.unique(outcomes)) == 2 else None
    return {
        "n": n,
        "positives": int(outcomes.sum()),
        "class_balance": float(outcomes.mean()),
        "log_loss": float(losses.mean()),
        "brier": float(np.mean((predictions - outcomes) ** 2)),
        "auroc": auroc,
        "auroc_eligible": auroc is not None,
        "accuracy": wilson(correct, n),
        "threshold": 0.5,
        "calibration": calibration_curve(outcomes, predictions, bins),
    }


def cluster_intervals(
    y: Any,
    p: Any,
    learners: list[str],
    repetitions: int = 200,
    seed: int = 0,
    confidence: float = 0.95,
) -> dict[str, Any]:
    outcomes, predictions = inputs(y, p)
    if len(learners) != len(outcomes):
        raise ValueError("Cluster labels must align with predictions")
    if not 20 <= repetitions <= 5000 or not 0 < confidence < 1:
        raise ValueError("Invalid bootstrap configuration")
    clusters, inverse = np.unique(learners, return_inverse=True)
    if len(clusters) < 2:
        return {
            "available": False,
            "reason": "At least two independent learner clusters are needed.",
            "clusters": len(clusters),
        }
    loss = -(outcomes * np.log(predictions) + (1 - outcomes) * np.log1p(-predictions))
    values = {
        "log_loss": loss,
        "brier": (predictions - outcomes) ** 2,
        "accuracy": ((predictions >= 0.5) == outcomes).astype(float),
    }
    totals = {
        key: np.bincount(inverse, weights=value, minlength=len(clusters))
        for key, value in values.items()
    }
    counts = np.bincount(inverse, minlength=len(clusters))
    rng = np.random.default_rng(seed)
    samples: dict[str, list[float]] = {key: [] for key in totals}
    for _ in range(repetitions):
        chosen = rng.integers(0, len(clusters), len(clusters))
        weights = np.bincount(chosen, minlength=len(clusters))
        denominator = weights @ counts
        for key, total in totals.items():
            samples[key].append(float(weights @ total / denominator))
    tail = (1 - confidence) / 2
    intervals = {
        key: {
            "lower": float(np.quantile(value, tail)),
            "upper": float(np.quantile(value, 1 - tail)),
        }
        for key, value in samples.items()
    }
    return {
        "available": True,
        "clusters": len(clusters),
        "repetitions": repetitions,
        "seed": seed,
        "confidence": confidence,
        "method": "Learner-cluster percentile bootstrap, whole histories preserved",
        "intervals": intervals,
        "auroc_interval": None,
    }


def paired_comparison(
    y: Any, a: Any, b: Any, learners: list[str], repetitions: int = 200, seed: int = 0
) -> dict[str, Any]:
    outcomes, pa = inputs(y, a)
    _, pb = inputs(y, b)
    if len(learners) != len(outcomes):
        raise ValueError("Paired rows and clusters do not align")
    loss_a = -(outcomes * np.log(pa) + (1 - outcomes) * np.log1p(-pa))
    loss_b = -(outcomes * np.log(pb) + (1 - outcomes) * np.log1p(-pb))
    clusters, inverse = np.unique(learners, return_inverse=True)
    if len(clusters) < 2:
        return {
            "available": False,
            "reason": "Paired resampling needs at least two learner clusters",
        }
    difference = np.bincount(inverse, weights=loss_a - loss_b, minlength=len(clusters))
    counts = np.bincount(inverse, minlength=len(clusters))
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(repetitions):
        weights = np.bincount(
            rng.integers(0, len(clusters), len(clusters)), minlength=len(clusters)
        )
        samples.append(float(weights @ difference / (weights @ counts)))
    return {
        "available": True,
        "n": len(outcomes),
        "clusters": len(clusters),
        "log_loss_a_minus_b": float(np.mean(loss_a - loss_b)),
        "lower": float(np.quantile(samples, 0.025)),
        "upper": float(np.quantile(samples, 0.975)),
        "repetitions": repetitions,
        "seed": seed,
        "method": "Paired learner-cluster bootstrap",
        "interpretation": "Negative differences favor model A; interval overlap with zero is inconclusive.",
    }
