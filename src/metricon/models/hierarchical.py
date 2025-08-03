from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.special import betaln, gammaln

from metricon.analytics.statistics import beta_summary
from metricon.models.base import probabilities, entity_key


class HierarchicalBetaBinomial:
    def __init__(self, dimension: str = "question", shrinkage: bool = True):
        if dimension not in {"question", "skill"}:
            raise ValueError("Unsupported hierarchical dimension")
        self.dimension = dimension
        self.shrinkage = shrinkage
        self.alpha = 1.0
        self.beta = 1.0
        self.counts: dict[str, tuple[int, int]] = {}
        self.diagnostics: dict[str, Any] = {}
        self.identity_encoding = "json-tuple/1"

    def groups(self, row: dict[str, Any]) -> list[str]:
        return (
            [entity_key(row, "question_id", self.identity_encoding)]
            if self.dimension == "question"
            else list(row["skills"])
        )

    def fit(self, rows: list[dict[str, Any]]) -> HierarchicalBetaBinomial:
        self.identity_encoding = "json-tuple/1"
        groups: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for row in rows:
            for key in self.groups(row):
                groups[key][0] += int(row["correct"])
                groups[key][1] += 1
        self.counts = {key: tuple(value) for key, value in groups.items()}
        self.alpha = self.beta = 1.0
        self.diagnostics = {
            "fitted": False,
            "groups": len(groups),
            "reason": "Unpooled uniform prior",
        }
        if self.shrinkage and len(groups) >= 3:
            successes = np.array([value[0] for value in groups.values()], dtype=float)
            n = np.array([value[1] for value in groups.values()], dtype=float)
            combinatorial = gammaln(n + 1) - gammaln(successes + 1) - gammaln(n - successes + 1)

            def objective(log_parameters: np.ndarray) -> float:
                a, b = np.exp(log_parameters)
                log_probability = (
                    combinatorial + betaln(successes + a, n - successes + b) - betaln(a, b)
                )
                return -float(log_probability.sum()) + 0.01 * float(log_parameters @ log_parameters)

            result = minimize(objective, np.zeros(2), method="L-BFGS-B", bounds=[(-5, 8), (-5, 8)])
            self.alpha, self.beta = map(float, np.exp(result.x))
            self.diagnostics = {
                "fitted": True,
                "converged": bool(result.success),
                "groups": len(groups),
                "objective": float(result.fun),
                "iterations": int(result.nit),
                "method": "Regularized marginal Beta-Binomial empirical Bayes, training only",
            }
        return self

    def summary(self, group: str) -> dict[str, Any]:
        successes, n = self.counts.get(group, (0, 0))
        return {
            "group": group,
            **beta_summary(successes, n, self.alpha, self.beta),
            "prior_alpha": self.alpha,
            "prior_beta": self.beta,
            "supported": n > 0,
        }

    def predict(self, rows: list[dict[str, Any]], update: bool = True) -> np.ndarray:
        result = []
        for row in rows:
            estimates = [self.summary(group)["mean"] for group in self.groups(row)]
            result.append(
                float(np.mean(estimates)) if estimates else self.alpha / (self.alpha + self.beta)
            )
        return probabilities(result)

    def parameters(self) -> dict[str, Any]:
        return {
            "family": "hierarchical",
            "identity_encoding": self.identity_encoding,
            "dimension": self.dimension,
            "shrinkage": self.shrinkage,
            "alpha": self.alpha,
            "beta": self.beta,
            "counts": self.counts,
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def restore(cls, payload: dict[str, Any]) -> HierarchicalBetaBinomial:
        model = cls(payload["dimension"], payload["shrinkage"])
        model.identity_encoding = payload.get("identity_encoding", "colon/legacy")
        model.alpha, model.beta = payload["alpha"], payload["beta"]
        model.counts = {key: tuple(value) for key, value in payload["counts"].items()}
        model.diagnostics = payload["diagnostics"]
        return model
