from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import numpy as np
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import MaxAbsScaler

from metricon.features.history import FeatureEncoder, HistoryFeatures, domain, labels, units
from metricon.models.base import probabilities, entity_key


class GlobalBaseline:
    def __init__(self, alpha: float = 1, beta: float = 1):
        if alpha <= 0 or beta <= 0:
            raise ValueError("Beta prior must be positive")
        self.alpha = alpha
        self.beta = beta
        self.n = 0
        self.successes = 0

    @property
    def probability(self) -> float:
        return (self.successes + self.alpha) / (self.n + self.alpha + self.beta)

    def fit(self, rows: list[dict[str, Any]]) -> GlobalBaseline:
        self.n = len(rows)
        self.successes = sum(int(row["correct"]) for row in rows)
        return self

    def predict(self, rows: list[dict[str, Any]], update: bool = True) -> np.ndarray:
        return probabilities(np.full(len(rows), self.probability))

    def parameters(self) -> dict[str, Any]:
        return {
            "family": "global",
            "alpha": self.alpha,
            "beta": self.beta,
            "n": self.n,
            "successes": self.successes,
            "p": self.probability,
        }

    @classmethod
    def restore(cls, payload: dict[str, Any]) -> GlobalBaseline:
        model = cls(payload["alpha"], payload["beta"])
        model.n = payload["n"]
        model.successes = payload["successes"]
        return model


class ItemPrior:
    def __init__(self, strength: float = 10):
        if strength <= 0:
            raise ValueError("Item prior strength must be positive")
        self.strength = strength
        self.global_model = GlobalBaseline()
        self.items: dict[str, tuple[int, int]] = {}
        self.identity_encoding = "json-tuple/1"

    def fit(self, rows: list[dict[str, Any]]) -> ItemPrior:
        self.global_model.fit(rows)
        self.identity_encoding = "json-tuple/1"
        values: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for row in rows:
            key = entity_key(row, "question_id", self.identity_encoding)
            values[key][0] += int(row["correct"])
            values[key][1] += 1
        self.items = {key: tuple(value) for key, value in values.items()}
        return self

    def predict(self, rows: list[dict[str, Any]], update: bool = True) -> np.ndarray:
        prior = self.global_model.probability
        result = []
        for row in rows:
            key = entity_key(row, "question_id", self.identity_encoding)
            successes, n = self.items.get(key, (0, 0))
            result.append((successes + self.strength * prior) / (n + self.strength))
        return probabilities(result)

    def parameters(self) -> dict[str, Any]:
        return {
            "family": "item_prior",
            "identity_encoding": self.identity_encoding,
            "strength": self.strength,
            "global": self.global_model.parameters(),
            "items": self.items,
        }

    @classmethod
    def restore(cls, payload: dict[str, Any]) -> ItemPrior:
        model = cls(payload["strength"])
        model.identity_encoding = payload.get("identity_encoding", "colon/legacy")
        model.global_model = GlobalBaseline.restore(payload["global"])
        model.items = {key: tuple(value) for key, value in payload["items"].items()}
        return model


class RecentHistory:
    def __init__(self, window: int = 10):
        if not 1 <= window <= 1000:
            raise ValueError("Recent window must be between 1 and 1000")
        self.window = window
        self.global_model = GlobalBaseline()
        self.history: dict[tuple[str, str, str], deque[int]] = defaultdict(
            lambda: deque(maxlen=window)
        )

    def fit(self, rows: list[dict[str, Any]]) -> RecentHistory:
        self.global_model.fit(rows)
        self.history.clear()
        for unit in units(rows):
            for row in unit:
                self.history[domain(row)].append(int(row["correct"]))
        return self

    def predict(self, rows: list[dict[str, Any]], update: bool = True) -> np.ndarray:
        lookup = {}
        for unit in units(rows):
            for row in unit:
                previous = self.history[domain(row)]
                prior = self.global_model.probability
                lookup[row["identity"]] = (sum(previous) + 2 * prior) / (len(previous) + 2)
            if update:
                for row in unit:
                    self.history[domain(row)].append(int(row["correct"]))
        return probabilities([lookup[row["identity"]] for row in rows])

    def parameters(self) -> dict[str, Any]:
        return {
            "family": "recent",
            "window": self.window,
            "global": self.global_model.parameters(),
            "history": [
                {"key": list(key), "values": list(value)}
                for key, value in sorted(self.history.items())
            ],
        }

    @classmethod
    def restore(cls, payload: dict[str, Any]) -> RecentHistory:
        model = cls(payload["window"])
        model.global_model = GlobalBaseline.restore(payload["global"])
        for entry in payload["history"]:
            model.history[tuple(entry["key"])].extend(entry["values"])
        return model


class LogisticHistory:
    def __init__(self, c: float = 1, seed: int = 0, skill_tags: bool = True, temporal: bool = True):
        if c <= 0:
            raise ValueError("Regularization C must be positive")
        self.c = c
        self.seed = seed
        self.skill_tags = skill_tags
        self.temporal = temporal
        self.history = HistoryFeatures(skill_tags, temporal)
        self.encoder = FeatureEncoder()
        self.coefficients = np.empty(0)
        self.feature_scales = np.empty(0)
        self.intercept = 0.0
        self.diagnostics: dict[str, Any] = {}
        self.training_rows: list[dict[str, Any]] = []

    def fit(self, rows: list[dict[str, Any]]) -> LogisticHistory:
        if not rows:
            raise ValueError("Logistic fitting requires nonempty training data")
        self.history = HistoryFeatures(self.skill_tags, self.temporal)
        features, ordered = self.history.transform(rows)
        matrix = self.encoder.fit_transform(features)
        scaler = MaxAbsScaler()
        matrix = scaler.fit_transform(matrix)
        self.feature_scales = scaler.scale_
        y = labels(ordered)
        if len(np.unique(y)) < 2:
            rate = (int(y.sum()) + 1) / (len(y) + 2)
            self.coefficients = np.zeros(matrix.shape[1])
            self.intercept = float(np.log(rate / (1 - rate)))
            self.diagnostics = {"converged": True, "single_class": True, "n": len(y)}
        else:
            model = LogisticRegression(
                C=self.c, max_iter=500, solver="lbfgs", random_state=self.seed
            )
            model.fit(matrix, y)
            self.coefficients = model.coef_[0]
            self.intercept = float(model.intercept_[0])
            self.diagnostics = {
                "converged": bool(model.n_iter_[0] < 500),
                "iterations": int(model.n_iter_[0]),
                "n": len(y),
            }
        self.training_rows = rows
        return self

    def predict(self, rows: list[dict[str, Any]], update: bool = True) -> np.ndarray:
        if not rows:
            return np.empty(0)
        features, ordered = self.history.transform(rows, update)
        matrix = self.encoder.transform(features)
        values = expit(matrix @ (self.coefficients / self.feature_scales) + self.intercept)
        lookup = {row["identity"]: value for row, value in zip(ordered, values)}
        return probabilities([lookup[row["identity"]] for row in rows])

    def associations(self, limit: int = 30) -> list[dict[str, Any]]:
        order = np.argsort(-np.abs(self.coefficients))[:limit]
        return [
            {
                "feature": self.encoder.names[index],
                "coefficient": float(self.coefficients[index]),
                "interpretation": "Predictive association, not a causal effect",
            }
            for index in order
        ]

    def parameters(self) -> dict[str, Any]:
        return {
            "family": "logistic",
            "c": self.c,
            "seed": self.seed,
            "skill_tags": self.skill_tags,
            "temporal": self.temporal,
            "encoder": self.encoder.parameters(),
            "history": self.history.snapshot(),
            "feature_scales": self.feature_scales.tolist(),
            "scaling_method": "Training-only maximum absolute feature scaling",
            "coefficients": self.coefficients.tolist(),
            "intercept": self.intercept,
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def restore(cls, payload: dict[str, Any]) -> LogisticHistory:
        model = cls(payload["c"], payload["seed"], payload["skill_tags"], payload["temporal"])
        model.encoder = FeatureEncoder.restore(payload["encoder"])
        model.history.restore_snapshot(payload["history"])
        model.coefficients = np.asarray(payload["coefficients"])
        model.feature_scales = np.asarray(
            payload.get("feature_scales", np.ones(len(model.coefficients)))
        )
        model.intercept = payload["intercept"]
        model.diagnostics = payload["diagnostics"]
        return model
