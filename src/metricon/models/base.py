from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import numpy as np

from metricon.storage.hashing import atomic_json, read_json

MODEL_VERSION = "models/1"
EPSILON = 1e-9


def probabilities(values: Any) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(array)):
        raise ValueError("Predictions contain nonfinite values")
    return np.clip(array, EPSILON, 1 - EPSILON)


class Predictor(Protocol):
    def fit(self, rows: list[dict[str, Any]]) -> Any: ...
    def predict(self, rows: list[dict[str, Any]], update: bool = True) -> np.ndarray: ...
    def parameters(self) -> dict[str, Any]: ...


def save_model(path: Path, model: Predictor) -> None:
    atomic_json(path, {"model_version": MODEL_VERSION, "parameters": model.parameters()})


def load_model(path: Path) -> Predictor:
    payload = read_json(path)
    if payload["model_version"] != MODEL_VERSION:
        raise ValueError("Unsupported model version")
    parameters = payload["parameters"]
    family = parameters["family"]
    from metricon.models.baselines import GlobalBaseline, ItemPrior, RecentHistory, LogisticHistory
    from metricon.models.bkt import BKT
    from metricon.models.hierarchical import HierarchicalBetaBinomial
    from metricon.models.irt import IRT

    classes = {
        "global": GlobalBaseline,
        "item_prior": ItemPrior,
        "recent": RecentHistory,
        "logistic": LogisticHistory,
        "bkt": BKT,
        "hierarchical": HierarchicalBetaBinomial,
        "irt": IRT,
    }
    if family not in classes:
        raise ValueError("Unknown model family")
    return classes[family].restore(parameters)
