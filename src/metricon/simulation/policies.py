from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from metricon.models.bkt import BKTParameters, step


@dataclass
class Belief:
    probability: float
    attempts: int = 0
    last_step: int = -1
    successes: int = 0


def choose_action(
    policy: str,
    beliefs: dict[str, Belief],
    rng: np.random.Generator,
    index: int,
    available: list[str],
    duration: dict[str, float],
) -> str:
    if not available:
        raise ValueError("No available simulated study action")
    if policy == "random":
        return str(rng.choice(available))
    if policy == "weakest":
        return min(available, key=lambda skill: (beliefs[skill].probability, skill))
    if policy == "uncertainty":
        return max(
            available,
            key=lambda skill: (
                beliefs[skill].probability
                * (1 - beliefs[skill].probability)
                / (beliefs[skill].attempts + 1),
                skill,
            ),
        )
    if policy == "spaced":
        return max(
            available,
            key=lambda skill: (
                index - beliefs[skill].last_step,
                -beliefs[skill].probability,
                skill,
            ),
        )
    if policy == "budget":
        return max(
            available, key=lambda skill: ((1 - beliefs[skill].probability) / duration[skill], skill)
        )
    raise ValueError("Unknown simulation policy")


def update_belief(
    belief: Belief, correct: bool, parameters: BKTParameters, index: int
) -> dict[str, Any]:
    prediction, posterior, following = step(belief.probability, correct, parameters)
    belief.probability = following
    belief.attempts += 1
    belief.successes += int(correct)
    belief.last_step = index
    return {
        "prediction_before": prediction,
        "posterior_after_answer": posterior,
        "knowledge_after_transition": following,
        "attempts": belief.attempts,
    }
