from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from metricon.analytics.statistics import beta_summary
from metricon.features.history import ordered_rows
from metricon.schema.events import digest
from metricon.storage.catalog import Catalog
from metricon.storage.query import analytical_connection, scan_events


@dataclass(frozen=True)
class PlannerConfig:
    budget_seconds: float = 900
    maximum_actions: int = 12
    priorities: dict[str, float] = field(default_factory=dict)
    prerequisites: dict[str, list[str]] = field(default_factory=dict)
    prerequisite_threshold: float = 0.6
    recent_window: int = 10
    minimum_duration_observations: int = 3
    uncertainty_weight: float = 0.4
    deficit_weight: float = 0.4
    priority_weight: float = 0.2
    available_questions: tuple[str, ...] = ()
    model_artifact_id: str | None = None
    model_weight: float = 0.2

    def validate(self) -> None:
        if not np.isfinite(self.budget_seconds) or self.budget_seconds <= 0:
            raise ValueError("Time budget must be a positive finite number")
        if not 1 <= self.maximum_actions <= 100 or not 0 <= self.recent_window <= 1000:
            raise ValueError("Invalid planner limits")
        if (
            not 0 < self.prerequisite_threshold < 1
            or not 1 <= self.minimum_duration_observations <= 1000
        ):
            raise ValueError("Invalid prerequisite or duration threshold")
        weights = [
            self.uncertainty_weight,
            self.deficit_weight,
            self.priority_weight,
            self.model_weight,
        ]
        if any(not np.isfinite(value) or value < 0 for value in weights) or sum(weights) <= 0:
            raise ValueError("Ranking weights must be finite, nonnegative, and not all zero")
        if any(not np.isfinite(value) or value < 0 for value in self.priorities.values()):
            raise ValueError("User priorities must be finite nonnegative values")
        visited: set[str] = set()
        active: set[str] = set()

        def visit(skill: str) -> None:
            if skill in active:
                raise ValueError("Prerequisite graph contains a cycle")
            if skill in visited:
                return
            active.add(skill)
            for prerequisite in self.prerequisites.get(skill, []):
                visit(prerequisite)
            active.remove(skill)
            visited.add(skill)

        for skill in self.prerequisites:
            visit(skill)


def plan(
    catalog: Catalog, dataset_id: str, learner_id: str, config: PlannerConfig
) -> dict[str, Any]:
    config.validate()
    frame = (
        scan_events(catalog, dataset_id)
        .filter(__import__("polars").col("learner_id") == learner_id)
        .collect()
    )
    rows = ordered_rows(frame.to_dicts())
    counts: dict[str, list[int]] = {}
    skills: dict[str, list[int]] = {}
    item_tags: dict[str, set[str]] = {}
    for row in rows:
        item = counts.setdefault(row["question_id"], [0, 0])
        item[0] += int(row["correct"])
        item[1] += 1
        item_tags.setdefault(row["question_id"], set()).update(row["skills"])
        for skill in row["skills"]:
            state = skills.setdefault(skill, [0, 0])
            state[0] += int(row["correct"])
            state[1] += 1
    order_available = (
        all(row["order_scope"] == "learner" for row in rows)
        and len({row["source_namespace"] for row in rows}) <= 1
    )
    recent = (
        {row["question_id"] for row in rows[-config.recent_window :]}
        if order_available and config.recent_window
        else set()
    )
    with analytical_connection(catalog, dataset_id) as connection:
        durations = connection.execute(
            """
            SELECT question_id,count(*) n,median(duration_ms)/1000 median_seconds,
              quantile_cont(duration_ms,.25)/1000 q25_seconds,quantile_cont(duration_ms,.75)/1000 q75_seconds
              FROM events WHERE learner_id=? AND duration_ms>0 AND duration_scope='event'
              GROUP BY question_id
        """,
            [learner_id],
        ).fetchall()
    duration_lookup = {
        row[0]: {
            "n": row[1],
            "median_seconds": row[2],
            "q25_seconds": row[3],
            "q75_seconds": row[4],
            "method": "Observed learner/item event-duration median",
        }
        for row in durations
    }
    model = None
    if config.model_artifact_id:
        from metricon.models.base import load_model
        from metricon.storage.artifacts import verify_artifact

        artifact = catalog.artifact(config.model_artifact_id)
        if artifact["dataset_id"] != dataset_id or artifact["kind"] != "experiment":
            raise ValueError("Planner model must belong to this exact dataset version")
        if not verify_artifact(catalog, config.model_artifact_id)["valid"]:
            raise ValueError("Planner model artifact checksum mismatch")
        model = load_model(
            catalog.root / "artifacts" / config.model_artifact_id / "fold-0/bkt.model.json"
        )
        model.states.clear()
        model.predict(rows, update=True)
    candidates = []
    available = set(config.available_questions) if config.available_questions else set(counts)
    maximum_priority = max([1.0, *config.priorities.values()])
    for question in sorted(available):
        successes, n = counts.get(question, [0, 0])
        posterior = beta_summary(successes, n)
        tags = sorted(item_tags.get(question, set()))
        blocked = []
        for skill in tags:
            for prerequisite in config.prerequisites.get(skill, []):
                prior_successes, prior_n = skills.get(prerequisite, [0, 0])
                lower = beta_summary(prior_successes, prior_n)["lower"]
                if prior_n == 0 or lower < config.prerequisite_threshold:
                    blocked.append(
                        {
                            "skill": prerequisite,
                            "observations": prior_n,
                            "lower_performance_bound": lower,
                        }
                    )
        priority = (
            max([config.priorities.get(skill, 1) for skill in tags] or [1]) / maximum_priority
        )
        contributions = {
            "performance_deficit": config.deficit_weight * (1 - posterior["mean"]),
            "uncertainty": config.uncertainty_weight * (posterior["upper"] - posterior["lower"]),
            "user_priority": config.priority_weight * priority,
            "recent_repetition": -0.25 if question in recent else 0.0,
        }
        model_state = None
        if model and tags and rows:
            hypothetical = {**rows[-1], "question_id": question, "skills": tags}
            model_state = model.explain(hypothetical)
            contributions["model_prediction_deficit"] = config.model_weight * (
                1 - model_state["prediction"]
            )
        score = sum(contributions.values())
        duration = duration_lookup.get(question)
        timed = duration is not None and duration["n"] >= config.minimum_duration_observations
        candidates.append(
            {
                "question_id": question,
                "skills": tags,
                "score": score,
                "contributions": contributions,
                "observed_performance": posterior,
                "model_state": model_state,
                "model_artifact_id": config.model_artifact_id,
                "duration": duration,
                "timed_eligible": timed,
                "prerequisite_blocks": blocked,
                "ranking_basis": "Observed performance uncertainty and user priorities; no causal gain claim",
            }
        )
    candidates.sort(key=lambda row: (-row["score"], row["question_id"]))
    selected = []
    unknown_time = []
    blocked_actions = []
    remaining = config.budget_seconds
    for candidate in candidates:
        if candidate["prerequisite_blocks"]:
            blocked_actions.append(candidate)
            continue
        if not candidate["timed_eligible"]:
            unknown_time.append(candidate)
            continue
        seconds = candidate["duration"]["median_seconds"]
        if seconds <= remaining and len(selected) < config.maximum_actions:
            selected.append({**candidate, "planned_seconds": seconds})
            remaining -= seconds
    configuration = {key: value for key, value in config.__dict__.items()}
    return {
        "dataset_id": dataset_id,
        "learner_id": learner_id,
        "configuration": configuration,
        "plan_hash": digest([dataset_id, learner_id, configuration]),
        "actions": selected,
        "budget_seconds": config.budget_seconds,
        "planned_seconds": config.budget_seconds - remaining,
        "remaining_seconds": remaining,
        "unknown_time_actions": unknown_time[:100],
        "blocked_actions": blocked_actions[:100],
        "candidates": len(candidates),
        "recent_order_available": order_available,
        "method": "Deterministic priority ranking with greedy observed-time budget allocation",
        "limits": [
            "Observed medians do not guarantee future completion within budget.",
            "No time estimate is fabricated for unknown or bundle-level durations.",
            "Prerequisites use observed-performance bounds and user-supplied structure, not certified mastery.",
        ],
    }
