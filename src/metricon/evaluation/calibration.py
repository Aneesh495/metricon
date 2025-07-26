from __future__ import annotations

from typing import Any

import numpy as np
from scipy.special import expit, logit
from sklearn.linear_model import LogisticRegression

from metricon.evaluation.metrics import inputs
from metricon.models.base import probabilities


class PlattCalibrator:
    def __init__(self):
        self.slope = 1.0
        self.intercept = 0.0
        self.diagnostics: dict[str, Any] = {"fitted": False}

    def fit(self, y: Any, p: Any) -> PlattCalibrator:
        outcomes, predictions = inputs(y, p)
        if len(outcomes) < 30 or len(np.unique(outcomes)) < 2:
            self.diagnostics = {
                "fitted": False,
                "n": len(outcomes),
                "reason": "Calibration requires 30 validation rows and both classes",
            }
            return self
        matrix = logit(predictions).reshape(-1, 1)
        model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500)
        model.fit(matrix, outcomes)
        self.slope = float(model.coef_[0, 0])
        self.intercept = float(model.intercept_[0])
        self.diagnostics = {
            "fitted": True,
            "n": len(outcomes),
            "converged": bool(model.n_iter_[0] < 500),
            "partition": "validation only",
            "method": "Regularized Platt logit calibration",
        }
        return self

    def predict(self, p: Any) -> np.ndarray:
        return probabilities(expit(self.slope * logit(probabilities(p)) + self.intercept))

    def parameters(self) -> dict[str, Any]:
        return {
            "version": "calibration/1",
            "slope": self.slope,
            "intercept": self.intercept,
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def restore(cls, payload: dict[str, Any]) -> PlattCalibrator:
        if payload["version"] != "calibration/1":
            raise ValueError("Unsupported calibration version")
        model = cls()
        model.slope = payload["slope"]
        model.intercept = payload["intercept"]
        model.diagnostics = payload["diagnostics"]
        return model
