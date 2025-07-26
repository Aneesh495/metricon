from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from metricon.schema.events import canonical_json


def learner_identity(row: dict[str, Any]) -> str:
    return canonical_json([row["source_namespace"], row["learner_id"]])


def item_identity(row: dict[str, Any]) -> str:
    return canonical_json([row["source_namespace"], row["question_id"]])


@dataclass(frozen=True)
class CohortRestrictions:
    minimum_learners: int = 20
    minimum_learner_responses: int = 10
    minimum_item_responses: int = 20
    minimum_items: int = 2
    largest_connected_component: bool = True
    max_pruning_passes: int = 100

    def validate(self) -> None:
        counts = [
            self.minimum_learners,
            self.minimum_learner_responses,
            self.minimum_item_responses,
            self.minimum_items,
            self.max_pruning_passes,
        ]
        if any(value < 1 for value in counts):
            raise ValueError("Cohort eligibility thresholds must be positive")


def eligible_cohort(
    rows: list[dict[str, Any]], restrictions: CohortRestrictions
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    restrictions.validate()
    current = list(rows)
    passes = []
    for index in range(restrictions.max_pruning_passes):
        learner_counts = Counter(learner_identity(row) for row in current)
        item_counts = Counter(item_identity(row) for row in current)
        learners = {
            key for key, n in learner_counts.items() if n >= restrictions.minimum_learner_responses
        }
        items = {key for key, n in item_counts.items() if n >= restrictions.minimum_item_responses}
        following = [
            row
            for row in current
            if learner_identity(row) in learners and item_identity(row) in items
        ]
        passes.append(
            {
                "pass": index,
                "before": len(current),
                "after": len(following),
                "eligible_learners": len(learners),
                "eligible_items": len(items),
            }
        )
        if len(following) == len(current):
            current = following
            break
        current = following
    else:
        raise ValueError("Cohort pruning failed to reach a fixed point within its bound")
    learners = sorted({learner_identity(row) for row in current})
    items = sorted({item_identity(row) for row in current})
    component_summary = []
    components = 0
    if current:
        learner_index = {key: index for index, key in enumerate(learners)}
        item_index = {key: index + len(learners) for index, key in enumerate(items)}
        left = np.array([learner_index[learner_identity(row)] for row in current])
        right = np.array([item_index[item_identity(row)] for row in current])
        matrix = coo_matrix(
            (np.ones(len(current)), (left, right)), shape=(len(learners) + len(items),) * 2
        )
        adjacency = (matrix + matrix.T).tocsr()
        components, labels = connected_components(adjacency, directed=False)
        counts = Counter(int(labels[index]) for index in left)
        for component in range(components):
            component_summary.append(
                {
                    "component": component,
                    "rows": counts.get(component, 0),
                    "learners": int(np.sum(labels[: len(learners)] == component)),
                    "items": int(np.sum(labels[len(learners) :] == component)),
                }
            )
        if restrictions.largest_connected_component and components > 1:
            chosen = max(component_summary, key=lambda value: (value["rows"], -value["component"]))[
                "component"
            ]
            current = [row for row, component in zip(current, labels[left]) if component == chosen]
    eligible_learners = {learner_identity(row) for row in current}
    eligible_items = {item_identity(row) for row in current}
    eligible = (
        len(eligible_learners) >= restrictions.minimum_learners
        and len(eligible_items) >= restrictions.minimum_items
        and len({row["correct"] for row in current}) == 2
    )
    report = {
        "eligible": eligible,
        "input_rows": len(rows),
        "retained_rows": len(current),
        "excluded_rows": len(rows) - len(current),
        "learners": len(eligible_learners),
        "items": len(eligible_items),
        "pruning_passes": passes,
        "connected_components_before_restriction": int(components),
        "components": component_summary,
        "restrictions": restrictions.__dict__,
        "interpretation": "Iterative response-count core and one connected learner/item graph. Different disconnected scales cannot be compared.",
    }
    return current, report
