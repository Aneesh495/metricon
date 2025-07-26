from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from metricon.features.history import units
from metricon.models.base import probabilities
from metricon.models.cohort import (
    CohortRestrictions,
    eligible_cohort,
    learner_identity,
    item_identity,
)


class IRTEligibilityError(ValueError):
    pass


class IRT:
    def __init__(
        self,
        parameters: int = 1,
        regularization: float = 1,
        minimum_learners: int = 20,
        minimum_item_responses: int = 20,
        minimum_learner_responses: int = 10,
        max_iterations: int = 150,
    ):
        if parameters not in {1, 2}:
            raise ValueError("IRT supports one or two parameters")
        if regularization <= 0:
            raise ValueError("IRT regularization must be positive")
        self.parameter_count = parameters
        self.regularization = regularization
        self.minimum_learners = minimum_learners
        self.minimum_item_responses = minimum_item_responses
        self.minimum_learner_responses = minimum_learner_responses
        self.max_iterations = max_iterations
        self.abilities: dict[str, float] = {}
        self.items: dict[str, dict[str, Any]] = {}
        self.diagnostics: dict[str, Any] = {}
        self.ability_precision: dict[str, float] = {}

    @staticmethod
    def learner_key(row: dict[str, Any]) -> str:
        return learner_identity(row)

    @staticmethod
    def item_key(row: dict[str, Any]) -> str:
        return item_identity(row)

    def fit(self, rows: list[dict[str, Any]]) -> IRT:
        original_rows = len(rows)
        rows, eligibility = eligible_cohort(
            rows,
            CohortRestrictions(
                self.minimum_learners, self.minimum_learner_responses, self.minimum_item_responses
            ),
        )
        if not eligibility["eligible"]:
            raise IRTEligibilityError(
                "Cohort graph and response-count restrictions leave insufficient supported population data"
            )
        learners = Counter(self.learner_key(row) for row in rows)
        items = Counter(self.item_key(row) for row in rows)
        selected_learners = sorted(
            key for key, n in learners.items() if n >= self.minimum_learner_responses
        )
        selected_items = sorted(key for key, n in items.items() if n >= self.minimum_item_responses)
        if len(selected_learners) < self.minimum_learners or len(selected_items) < 2:
            raise IRTEligibilityError(
                "Population IRT requires enough distinct eligible learners and items; sparse personal history is unsupported"
            )
        learner_index = {key: index for index, key in enumerate(selected_learners)}
        item_index = {key: index for index, key in enumerate(selected_items)}
        eligible = [
            row
            for row in rows
            if self.learner_key(row) in learner_index and self.item_key(row) in item_index
        ]
        if not eligible or len({row["correct"] for row in eligible}) < 2:
            raise IRTEligibilityError("IRT requires both observed answer classes")
        li = np.array([learner_index[self.learner_key(row)] for row in eligible])
        qi = np.array([item_index[self.item_key(row)] for row in eligible])
        y = np.array([int(row["correct"]) for row in eligible])
        l_count, q_count = len(selected_learners), len(selected_items)
        learner_success = np.bincount(li, weights=y, minlength=l_count)
        learner_n = np.bincount(li, minlength=l_count)
        initial_ability = np.log((learner_success + 1) / (learner_n - learner_success + 1))
        initial_ability -= initial_ability.mean()
        if np.std(initial_ability) < 0.01:
            initial_ability = np.linspace(-0.1, 0.1, l_count)
        initial = np.r_[
            initial_ability,
            np.zeros(q_count),
            np.zeros(q_count) if self.parameter_count == 2 else [],
        ]

        def objective(values: np.ndarray) -> tuple[float, np.ndarray]:
            raw = values[:l_count]
            center = raw - raw.mean()
            scale = np.sqrt(np.mean(center**2) + 1e-8) if self.parameter_count == 2 else 1.0
            theta = center / scale
            difficulty = values[l_count : l_count + q_count]
            log_discrimination = (
                values[l_count + q_count :] if self.parameter_count == 2 else np.zeros(q_count)
            )
            discrimination = np.exp(log_discrimination)
            logits = discrimination[qi] * (theta[li] - difficulty[qi])
            loss = float(np.sum(np.logaddexp(0, logits) - y * logits))
            residual = expit(logits) - y
            g_theta = np.bincount(li, weights=residual * discrimination[qi], minlength=l_count)
            g_difficulty = np.bincount(
                qi, weights=-residual * discrimination[qi], minlength=q_count
            )
            loss += 0.5 * self.regularization * float(difficulty @ difficulty + theta @ theta)
            g_difficulty += self.regularization * difficulty
            g_theta += self.regularization * theta
            if self.parameter_count == 2:
                g_raw = (g_theta - g_theta.mean() - theta * np.mean(g_theta * theta)) / scale
                g_discrimination = np.bincount(qi, weights=residual * logits, minlength=q_count)
                loss += self.regularization * float(log_discrimination @ log_discrimination)
                g_discrimination += 2 * self.regularization * log_discrimination
                gradient = np.r_[g_raw, g_difficulty, g_discrimination]
            else:
                gradient = np.r_[g_theta - g_theta.mean(), g_difficulty]
            return loss, gradient

        bounds = [(None, None)] * l_count + [(-6, 6)] * q_count
        if self.parameter_count == 2:
            bounds += [(np.log(0.25), np.log(3.0))] * q_count
        result = minimize(
            objective,
            initial,
            jac=True,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": self.max_iterations, "ftol": 1e-8},
        )
        theta = result.x[:l_count] - result.x[:l_count].mean()
        if self.parameter_count == 2:
            theta /= np.sqrt(np.mean(theta**2) + 1e-8)
        difficulty = result.x[l_count : l_count + q_count]
        discrimination = (
            np.exp(result.x[l_count + q_count :]) if self.parameter_count == 2 else np.ones(q_count)
        )
        self.abilities = dict(zip(selected_learners, map(float, theta)))
        p = expit(discrimination[qi] * (theta[li] - difficulty[qi]))
        information = np.bincount(
            qi, weights=discrimination[qi] ** 2 * p * (1 - p), minlength=q_count
        )
        learner_information = np.bincount(
            li, weights=discrimination[qi] ** 2 * p * (1 - p), minlength=l_count
        )
        self.ability_precision = dict(
            zip(selected_learners, map(float, learner_information + self.regularization))
        )
        item_counts = np.bincount(qi, minlength=q_count)
        for index, key in enumerate(selected_items):
            self.items[key] = {
                "difficulty": float(difficulty[index]),
                "discrimination": float(discrimination[index]),
                "n": int(item_counts[index]),
                "information": float(information[index]),
                "conditional_standard_error": float(
                    1 / np.sqrt(information[index] + self.regularization)
                ),
                "unstable": bool(information[index] < 5 or abs(difficulty[index]) > 5.9),
                "supported": True,
            }
        self.diagnostics = {
            "converged": bool(result.success),
            "message": str(result.message),
            "iterations": int(result.nit),
            "objective": float(result.fun),
            "eligible_rows": len(eligible),
            "excluded_rows": original_rows - len(eligible),
            "cohort_eligibility": eligibility,
            "learners": l_count,
            "items": q_count,
            "identifiability": "centered ability; unit variance in 2PL; fixed discrimination=1 in 1PL",
            "ability_mean": float(theta.mean()),
            "ability_sd": float(theta.std()),
            "standard_error_limit": "Conditional curvature approximation, not a joint posterior interval",
        }
        return self

    def predict(self, rows: list[dict[str, Any]], update: bool = True) -> np.ndarray:
        lookup = {}
        for unit in units(rows):
            for row in unit:
                ability = self.abilities.get(self.learner_key(row), 0.0)
                item = self.items.get(self.item_key(row))
                lookup[row["identity"]] = (
                    float(expit(item["discrimination"] * (ability - item["difficulty"])))
                    if item
                    else 0.5
                )
            if update:
                for row in unit:
                    item = self.items.get(self.item_key(row))
                    if item is None:
                        continue
                    key = self.learner_key(row)
                    ability = self.abilities.get(key, 0.0)
                    prediction = expit(item["discrimination"] * (ability - item["difficulty"]))
                    precision = self.ability_precision.get(key, self.regularization)
                    precision += item["discrimination"] ** 2 * prediction * (1 - prediction)
                    ability += (
                        item["discrimination"] * (int(row["correct"]) - prediction) / precision
                    )
                    self.abilities[key] = float(np.clip(ability, -6, 6))
                    self.ability_precision[key] = float(precision)
        return probabilities([lookup[row["identity"]] for row in rows])

    def parameters(self) -> dict[str, Any]:
        return {
            "family": "irt",
            "parameters": self.parameter_count,
            "regularization": self.regularization,
            "minimum_learners": self.minimum_learners,
            "minimum_item_responses": self.minimum_item_responses,
            "minimum_learner_responses": self.minimum_learner_responses,
            "max_iterations": self.max_iterations,
            "abilities": self.abilities,
            "ability_precision": self.ability_precision,
            "items": self.items,
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def restore(cls, payload: dict[str, Any]) -> IRT:
        model = cls(
            payload["parameters"],
            payload["regularization"],
            payload["minimum_learners"],
            payload["minimum_item_responses"],
            payload["minimum_learner_responses"],
            payload["max_iterations"],
        )
        model.abilities = payload["abilities"]
        model.items = payload["items"]
        model.ability_precision = payload["ability_precision"]
        model.diagnostics = payload["diagnostics"]
        return model
