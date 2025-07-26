from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import beta, norm


def wilson(successes: int, observations: int, confidence: float = 0.95) -> dict[str, Any]:
    if observations < 0 or successes < 0 or successes > observations:
        raise ValueError("Invalid numerator or denominator")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between zero and one")
    if observations == 0:
        return {
            "estimate": None,
            "lower": None,
            "upper": None,
            "n": 0,
            "successes": 0,
            "method": "Wilson",
            "confidence": confidence,
        }
    z = float(norm.ppf((1 + confidence) / 2))
    p = successes / observations
    denominator = 1 + z * z / observations
    center = (p + z * z / (2 * observations)) / denominator
    half = z * math.sqrt(p * (1 - p) / observations + z * z / (4 * observations**2)) / denominator
    return {
        "estimate": p,
        "lower": max(0.0, center - half),
        "upper": min(1.0, center + half),
        "n": observations,
        "successes": successes,
        "method": "Wilson",
        "confidence": confidence,
    }


def beta_summary(
    successes: int,
    observations: int,
    alpha: float = 1,
    beta_prior: float = 1,
    confidence: float = 0.95,
) -> dict[str, Any]:
    if (
        observations < successes
        or successes < 0
        or observations < 0
        or alpha <= 0
        or beta_prior <= 0
    ):
        raise ValueError("Invalid Beta posterior inputs")
    a = alpha + successes
    b = beta_prior + observations - successes
    tail = (1 - confidence) / 2
    return {
        "mean": a / (a + b),
        "lower": float(beta.ppf(tail, a, b)),
        "upper": float(beta.ppf(1 - tail, a, b)),
        "alpha": a,
        "beta": b,
        "n": observations,
        "successes": successes,
        "confidence": confidence,
        "interpretation": "Observed performance probability, not latent mastery",
    }


def quantile_summary(values: list[float] | np.ndarray) -> dict[str, Any]:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if len(array) == 0:
        return {"n": 0, "median": None, "q25": None, "q75": None, "p90": None, "mean": None}
    return {
        "n": len(array),
        "median": float(np.median(array)),
        "q25": float(np.quantile(array, 0.25)),
        "q75": float(np.quantile(array, 0.75)),
        "p90": float(np.quantile(array, 0.9)),
        "mean": float(array.mean()),
    }


def midrank_percentile(value: float, peers: np.ndarray) -> float | None:
    array = np.asarray(peers, dtype=float)
    array = array[np.isfinite(array)]
    if not len(array):
        return None
    return float(100 * (np.sum(array < value) + 0.5 * np.sum(array == value)) / len(array))
