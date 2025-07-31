from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize

from metricon.features.history import domain, units
from metricon.models.base import EPSILON, probabilities


@dataclass(frozen=True)
class BKTParameters:
    initial: float = 0.2
    learning: float = 0.1
    slip: float = 0.1
    guess: float = 0.2
    forgetting: float = 0.0

    def __post_init__(self) -> None:
        if any(not np.isfinite(value) or not 0 <= value <= 1 for value in asdict(self).values()):
            raise ValueError("BKT parameters must be finite probabilities")
        if self.slip + self.guess >= 1:
            raise ValueError("BKT requires known-state success greater than unknown-state success")


def step(prior: float, correct: bool, parameters: BKTParameters) -> tuple[float, float, float]:
    prediction = prior * (1 - parameters.slip) + (1 - prior) * parameters.guess
    numerator = prior * ((1 - parameters.slip) if correct else parameters.slip)
    evidence = prediction if correct else 1 - prediction
    posterior = numerator / max(evidence, EPSILON)
    following = posterior * (1 - parameters.forgetting) + (1 - posterior) * parameters.learning
    return float(prediction), float(np.clip(posterior, 0, 1)), float(np.clip(following, 0, 1))


def padded_sequences(sequences: list[list[int]], max_cells: int = 8_000_000) -> list[np.ndarray]:
    return [
        values
        for values, _ in padded_units(
            sequences, [[1] * len(sequence) for sequence in sequences], max_cells
        )
    ]


def padded_units(
    sequences: list[list[int]], starts: list[list[int]], max_cells: int = 8_000_000
) -> list[tuple[np.ndarray, np.ndarray]]:
    ordered = sorted(zip(sequences, starts), key=lambda pair: len(pair[0]))
    chunks = []
    pending = []
    for sequence, unit_starts in ordered:
        if not sequence:
            continue
        if len(sequence) != len(unit_starts):
            raise ValueError("BKT observations and unit markers must align")
        if pending and len(sequence) * (len(pending) + 1) > max_cells:
            chunks.append(
                (_pad([pair[0] for pair in pending]), _pad([pair[1] for pair in pending]))
            )
            pending = []
        pending.append((sequence, unit_starts))
    if pending:
        chunks.append((_pad([pair[0] for pair in pending]), _pad([pair[1] for pair in pending])))
    return chunks


def _pad(sequences: list[list[int]]) -> np.ndarray:
    array = np.full((max(map(len, sequences)), len(sequences)), -1, dtype=np.int8)
    for column, sequence in enumerate(sequences):
        array[: len(sequence), column] = sequence
    return array


def _prediction_derivative(
    k: np.ndarray, dk: np.ndarray, slip: float, guess: float
) -> tuple[np.ndarray, np.ndarray]:
    prediction = np.clip(guess + k * (1 - slip - guess), EPSILON, 1 - EPSILON)
    derivative = dk * (1 - slip - guess)
    derivative[:, 2] -= k
    derivative[:, 3] += 1 - k
    return prediction, derivative


def forward_objective(
    parameters: np.ndarray,
    matrices: list[np.ndarray],
    forgetting: bool = False,
    unit_starts: list[np.ndarray] | None = None,
) -> tuple[float, np.ndarray]:
    initial, learning, slip, guess = parameters[:4]
    forget = parameters[4] if forgetting else 0.0
    dimension = len(parameters)
    total = 0.0
    gradient = np.zeros(dimension)
    for matrix_index, matrix in enumerate(matrices):
        knowledge = np.full(matrix.shape[1], initial)
        derivative = np.zeros((matrix.shape[1], dimension))
        derivative[:, 0] = 1.0
        held_knowledge = knowledge.copy()
        held_derivative = derivative.copy()
        for index, observations in enumerate(matrix):
            active = observations >= 0
            if not active.any():
                continue
            fresh = (
                active if unit_starts is None else active & (unit_starts[matrix_index][index] == 1)
            )
            held_knowledge[fresh] = knowledge[fresh]
            held_derivative[fresh] = derivative[fresh]
            k, dk = knowledge[active], derivative[active]
            y = observations[active]
            prediction, dp = _prediction_derivative(
                held_knowledge[active], held_derivative[active], slip, guess
            )
            evidence = np.where(y == 1, prediction, 1 - prediction)
            de = dp * np.where(y == 1, 1, -1)[:, None]
            total -= float(np.log(evidence).sum())
            gradient -= (de / evidence[:, None]).sum(axis=0)
            instant_prediction, instant_derivative = _prediction_derivative(k, dk, slip, guess)
            instant_evidence = np.where(y == 1, instant_prediction, 1 - instant_prediction)
            instant_de = instant_derivative * np.where(y == 1, 1, -1)[:, None]
            known_likelihood = np.where(y == 1, 1 - slip, slip)
            numerator = k * known_likelihood
            dn = dk * known_likelihood[:, None]
            dn[:, 2] += k * np.where(y == 1, -1, 1)
            posterior = numerator / instant_evidence
            dposterior = (
                dn * instant_evidence[:, None] - numerator[:, None] * instant_de
            ) / instant_evidence[:, None] ** 2
            following = posterior * (1 - forget) + (1 - posterior) * learning
            dfollowing = dposterior * (1 - forget - learning)
            dfollowing[:, 1] += 1 - posterior
            if forgetting:
                dfollowing[:, 4] -= posterior
            knowledge[active] = np.clip(following, EPSILON, 1 - EPSILON)
            derivative[active] = dfollowing
    return total, gradient


class BKT:
    def __init__(
        self,
        seed: int = 0,
        starts: int = 3,
        forgetting: bool = False,
        multi_skill: str = "primary",
        minimum_observations: int = 30,
        max_iterations: int = 120,
    ):
        if not 1 <= starts <= 10:
            raise ValueError("BKT multi-start is bounded to 1..10")
        if multi_skill not in {"primary", "mean"}:
            raise ValueError("Multi-skill policy must be primary or mean")
        self.seed = seed
        self.starts = starts
        self.forgetting = forgetting
        self.multi_skill = multi_skill
        self.minimum_observations = minimum_observations
        self.max_iterations = max_iterations
        self.parameters_by_skill: dict[str, BKTParameters] = {}
        self.diagnostics: dict[str, dict[str, Any]] = {}
        self.states: dict[tuple[Any, ...], float] = {}
        self.global_probability = 0.5

    def selected_skills(self, row: dict[str, Any]) -> list[str]:
        skills = row["skills"]
        if not skills:
            return []
        return [skills[0]] if self.multi_skill == "primary" else list(skills)

    def fit(self, rows: list[dict[str, Any]]) -> BKT:
        self.global_probability = (sum(int(row["correct"]) for row in rows) + 1) / (len(rows) + 2)
        sequences: dict[str, dict[tuple[str, str, str], list[int]]] = defaultdict(
            lambda: defaultdict(list)
        )
        starts = defaultdict(lambda: defaultdict(list))
        for unit in units(rows):
            seen = set()
            for row in unit:
                for skill in self.selected_skills(row):
                    key = (skill, domain(row))
                    sequences[skill][domain(row)].append(int(row["correct"]))
                    starts[skill][domain(row)].append(int(key not in seen))
                    seen.add(key)
        rng = np.random.default_rng(self.seed)
        bounds = [(0.001, 0.999), (0.0001, 0.6), (0.001, 0.4), (0.001, 0.4)]
        if self.forgetting:
            bounds.append((0, 0.3))
        for skill in sorted(sequences):
            values = list(sequences[skill].values())
            n = sum(map(len, values))
            if n < self.minimum_observations or len(values) < 2:
                self.parameters_by_skill[skill] = BKTParameters()
                self.diagnostics[skill] = {
                    "fitted": False,
                    "reason": "Sparse skill; default parameters are explicit",
                    "n": n,
                    "sequences": len(values),
                }
                continue
            padded = padded_units(values, list(starts[skill].values()))
            matrices = [pair[0] for pair in padded]
            markers = [pair[1] for pair in padded]
            fits = []
            for start in range(self.starts):
                initial = np.array([0.2, 0.1, 0.1, 0.2] + ([0.02] if self.forgetting else []))
                if start:
                    initial = np.array([rng.uniform(low, high) for low, high in bounds])
                fit = minimize(
                    forward_objective,
                    initial,
                    args=(matrices, self.forgetting, markers),
                    jac=True,
                    method="L-BFGS-B",
                    bounds=bounds,
                    options={"maxiter": self.max_iterations, "ftol": 1e-8},
                )
                fits.append(fit)
            best = min(fits, key=lambda value: value.fun)
            values_p = best.x.tolist() + ([] if self.forgetting else [0.0])
            self.parameters_by_skill[skill] = BKTParameters(*values_p)
            self.diagnostics[skill] = {
                "fitted": True,
                "converged": bool(best.success),
                "message": str(best.message),
                "negative_composite_log_score": float(best.fun),
                "objective": "Marginal pre-unit log scores; delayed source-ordered conditioning and per-opportunity transitions. Standard likelihood when units have one skill observation.",
                "n": n,
                "sequences": len(sequences[skill]),
                "iterations": int(best.nit),
                "starts": self.starts,
                "boundary_parameters": [
                    index
                    for index, (value, bound) in enumerate(zip(best.x, bounds))
                    if abs(value - bound[0]) < 0.001 or abs(value - bound[1]) < 0.001
                ],
                "start_objectives": [float(value.fun) for value in fits],
            }
        self.states.clear()
        self.predict(rows, update=True)
        return self

    def state_key(self, row: dict[str, Any], skill: str) -> tuple[Any, ...]:
        return (*domain(row), skill)

    def explain(self, row: dict[str, Any]) -> dict[str, Any]:
        skill_states = []
        for skill in self.selected_skills(row):
            parameters = self.parameters_by_skill.get(skill, BKTParameters())
            prior = self.states.get(self.state_key(row, skill), parameters.initial)
            prediction = prior * (1 - parameters.slip) + (1 - prior) * parameters.guess
            skill_states.append(
                {
                    "skill": skill,
                    "prior_knowledge": prior,
                    "predicted_correct": prediction,
                    "parameters": asdict(parameters),
                    "diagnostics": self.diagnostics.get(skill, {"fitted": False}),
                }
            )
        prediction = (
            float(np.mean([state["predicted_correct"] for state in skill_states]))
            if skill_states
            else self.global_probability
        )
        return {
            "prediction": prediction,
            "skills": skill_states,
            "policy": self.multi_skill,
            "interpretation": "Latent posterior is a model estimate, not certified knowledge.",
        }

    def predict(self, rows: list[dict[str, Any]], update: bool = True) -> np.ndarray:
        lookup = {}
        for unit in units(rows):
            for row in unit:
                lookup[row["identity"]] = self.explain(row)["prediction"]
            if update:
                for row in unit:
                    for skill in self.selected_skills(row):
                        parameters = self.parameters_by_skill.get(skill, BKTParameters())
                        key = self.state_key(row, skill)
                        prior = self.states.get(key, parameters.initial)
                        _, _, following = step(prior, row["correct"], parameters)
                        self.states[key] = following
        return probabilities([lookup[row["identity"]] for row in rows])

    def parameters(self) -> dict[str, Any]:
        return {
            "family": "bkt",
            "seed": self.seed,
            "starts": self.starts,
            "forgetting": self.forgetting,
            "multi_skill": self.multi_skill,
            "minimum_observations": self.minimum_observations,
            "max_iterations": self.max_iterations,
            "global_probability": self.global_probability,
            "skills": {key: asdict(value) for key, value in self.parameters_by_skill.items()},
            "diagnostics": self.diagnostics,
            "states": [
                {"key": list(key), "value": value} for key, value in sorted(self.states.items())
            ],
            "transition": "predict before answer, condition on answer, then learning/forgetting per opportunity",
            "bundle_policy": "all predictions before any answer in the same session/timestamp unit",
        }

    @classmethod
    def restore(cls, payload: dict[str, Any]) -> BKT:
        model = cls(
            payload["seed"],
            payload["starts"],
            payload["forgetting"],
            payload["multi_skill"],
            payload["minimum_observations"],
            payload["max_iterations"],
        )
        model.parameters_by_skill = {
            key: BKTParameters(**value) for key, value in payload["skills"].items()
        }
        model.diagnostics = payload["diagnostics"]
        model.global_probability = payload["global_probability"]
        model.states = {tuple(entry["key"]): entry["value"] for entry in payload["states"]}
        return model
