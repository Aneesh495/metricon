from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from metricon.models.bkt import BKTParameters
from metricon.schema.events import digest
from metricon.simulation.policies import Belief, choose_action, update_belief


@dataclass(frozen=True)
class SimulationConfig:
    seed: int = 2026
    repetitions: int = 200
    budget_seconds: float = 900
    skills: tuple[str, ...] = ("algebra", "probability", "logic")
    policies: tuple[str, ...] = ("random", "weakest", "uncertainty", "spaced", "budget")
    duration_seconds: dict[str, float] = field(default_factory=dict)
    parameters: dict[str, dict[str, float]] = field(default_factory=dict)
    assumed_duration_seconds: float = 60
    max_actions: int = 1000
    trajectory_repetitions: int = 2
    regime: str = "nominal"
    budget_mode: str = "time"
    question_budget: int = 15
    retain_all_trajectories: bool = False
    policy_parameters: dict[str, dict[str, float]] = field(default_factory=dict)

    def validate(self) -> None:
        if not 2 <= self.repetitions <= 5000 or not 1 <= self.max_actions <= 10000:
            raise ValueError("Invalid Monte Carlo or action bounds")
        if self.regime not in {"nominal", "slow_learning", "forgetting", "misspecified"}:
            raise ValueError("Unknown simulator regime")
        if (
            self.budget_mode not in {"time", "questions"}
            or not 1 <= self.question_budget <= self.max_actions
        ):
            raise ValueError("Invalid equal-budget simulation mode")
        if not self.skills or len(self.skills) > 1000 or len(set(self.skills)) != len(self.skills):
            raise ValueError("Skills must be a nonempty unique bounded list")
        if (
            not self.policies
            or len(set(self.policies)) != len(self.policies)
            or not set(self.policies).issubset(
                {"random", "weakest", "uncertainty", "spaced", "budget"}
            )
        ):
            raise ValueError("Simulation policies must be unique and supported")
        values = [
            self.budget_seconds,
            self.assumed_duration_seconds,
            *self.duration_seconds.values(),
        ]
        if any(not np.isfinite(value) or value <= 0 for value in values):
            raise ValueError("Simulated time assumptions must be finite positive values")
        if min(
            self.duration_seconds.get(skill, self.assumed_duration_seconds)
            for skill in self.skills
        ) > self.budget_seconds:
            raise ValueError("Simulation time budget cannot fund an available action")
        for skill in self.skills:
            BKTParameters(**self.parameters.get(skill, {}))

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


def simulate(
    config: SimulationConfig,
    progress: Callable[[float, str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    config.validate()
    if cancelled and cancelled():
        raise RuntimeError("Cooperative task cancellation")
    skills = list(config.skills)
    duration = {
        skill: config.duration_seconds.get(skill, config.assumed_duration_seconds)
        for skill in skills
    }
    parameters = {skill: BKTParameters(**config.parameters.get(skill, {})) for skill in skills}
    assumed = {
        skill: BKTParameters(
            **config.policy_parameters.get(skill, config.parameters.get(skill, {}))
        )
        for skill in skills
    }
    if config.regime == "slow_learning":
        parameters = {
            skill: BKTParameters(**{**vars(value), "learning": value.learning * 0.25})
            for skill, value in parameters.items()
        }
    elif config.regime == "forgetting":
        parameters = {
            skill: BKTParameters(**{**vars(value), "forgetting": 0.12})
            for skill, value in parameters.items()
        }
    elif config.regime == "misspecified":
        parameters = {
            skill: BKTParameters(
                **{
                    **vars(value),
                    "learning": 0.02 if index == 0 else 0.22,
                    "slip": 0.35,
                    "guess": 0.35,
                    "forgetting": 0.15,
                }
            )
            for index, (skill, value) in enumerate(parameters.items())
        }
    outcomes = []
    trajectories = []
    results: dict[str, list[dict[str, float]]] = {policy: [] for policy in config.policies}
    total_trials = config.repetitions * len(config.policies)
    for repetition in range(config.repetitions):
        if cancelled and cancelled():
            raise RuntimeError("Cooperative task cancellation")
        replicate_seed = config.seed + repetition
        environmental_rng = np.random.default_rng(np.random.SeedSequence([replicate_seed, 0]))
        random_values = environmental_rng.random((config.max_actions + 1, len(skills), 3))
        skill_index = {skill: index for index, skill in enumerate(skills)}
        for policy in config.policies:
            policy_rng = np.random.default_rng(np.random.SeedSequence([replicate_seed, 1]))
            known = {
                skill: bool(random_values[0, skill_index[skill], 0] < parameters[skill].initial)
                for skill in skills
            }
            beliefs = {skill: Belief(assumed[skill].initial) for skill in skills}
            elapsed = 0.0
            successes = 0
            actions = 0
            history = []
            for index in range(
                min(config.max_actions, config.question_budget)
                if config.budget_mode == "questions"
                else config.max_actions
            ):
                if cancelled and cancelled():
                    raise RuntimeError("Cooperative task cancellation")
                available = [
                    skill for skill in skills if elapsed + duration[skill] <= config.budget_seconds
                ]
                if not available:
                    break
                skill = choose_action(policy, beliefs, policy_rng, index, available, duration)
                parameter = parameters[skill]
                noise = random_values[index + 1, skill_index[skill]]
                success_probability = 1 - parameter.slip if known[skill] else parameter.guess
                correct = bool(noise[0] < success_probability)
                was_known = known[skill]
                if was_known:
                    known[skill] = not bool(noise[1] < parameter.forgetting)
                else:
                    known[skill] = bool(noise[2] < parameter.learning)
                explanation = update_belief(beliefs[skill], correct, assumed[skill], index)
                elapsed += duration[skill]
                successes += int(correct)
                actions += 1
                if config.retain_all_trajectories or repetition < config.trajectory_repetitions:
                    history.append(
                        {
                            "step": index,
                            "skill": skill,
                            "correct": correct,
                            "elapsed_seconds": elapsed,
                            "simulated_latent_before": was_known,
                            "simulated_latent_after": known[skill],
                            "policy_belief": explanation,
                        }
                    )
            result = {
                "accuracy": successes / actions,
                "actions": float(actions),
                "simulated_latent_known_fraction": sum(known.values()) / len(skills),
                "elapsed_seconds": elapsed,
            }
            results[policy].append(result)
            outcomes.append(
                {"seed": replicate_seed, "policy": policy, "regime": config.regime, **result}
            )
            if config.retain_all_trajectories or repetition < config.trajectory_repetitions:
                trajectories.append(
                    {
                        "policy": policy,
                        "repetition": repetition,
                        "seed": replicate_seed,
                        "regime": config.regime,
                        "events": history,
                        "result": result,
                    }
                )
            if progress:
                progress(
                    len(outcomes) / total_trials,
                    f"Completed {len(outcomes)} of {total_trials} policy trials",
                )
    summaries = {}
    for policy, repetitions in results.items():
        summaries[policy] = {}
        for metric in repetitions[0]:
            array = np.asarray([result[metric] for result in repetitions])
            standard_error = array.std(ddof=1) / np.sqrt(len(array))
            summaries[policy][metric] = {
                "mean": float(array.mean()),
                "standard_error": float(standard_error),
                "lower": float(array.mean() - 1.96 * standard_error),
                "upper": float(array.mean() + 1.96 * standard_error),
                "n": len(array),
            }
    paired = {}
    reference = config.policies[0]
    for policy in config.policies[1:]:
        difference = np.asarray(
            [
                a["simulated_latent_known_fraction"] - b["simulated_latent_known_fraction"]
                for a, b in zip(results[policy], results[reference])
            ]
        )
        error = difference.std(ddof=1) / np.sqrt(len(difference))
        paired[policy] = {
            "reference": reference,
            "mean_difference": float(difference.mean()),
            "lower": float(difference.mean() - 1.96 * error),
            "upper": float(difference.mean() + 1.96 * error),
            "method": "Paired Monte Carlo means using common environmental random numbers",
        }
    return {
        "simulation_version": "policy-simulation/2",
        "configuration": config.as_dict(),
        "simulation_hash": digest(config.as_dict()),
        "synthetic": True,
        "summaries": summaries,
        "outcomes": outcomes,
        "seeds": [config.seed + repetition for repetition in range(config.repetitions)],
        "environment_parameters": {skill: vars(value) for skill, value in parameters.items()},
        "policy_assumptions": {skill: vars(value) for skill, value in assumed.items()},
        "regime": config.regime,
        "budget_mode": config.budget_mode,
        "paired_comparisons": paired,
        "trajectories": trajectories,
        "assumptions": {
            "time": "Explicit simulation duration assumptions; not estimates from missing observed data",
            "environment": "Binary latent BKT process; transitions per selected opportunity",
            "policy_information": "Policies receive answer-conditioned beliefs, never simulated latent state",
        },
        "interpretation": "Synthetic policy comparison conditional on assumptions; does not establish real-world causal benefit.",
    }
