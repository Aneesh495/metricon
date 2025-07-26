from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np

from metricon.features.history import domain, units
from metricon.schema.events import digest

SPLIT_VERSION = "splits/1"


@dataclass(frozen=True)
class SplitManifest:
    assignments: dict[str, str]
    mode: str
    seed: int
    parameters: dict[str, Any]
    version: str = SPLIT_VERSION

    @property
    def hash(self) -> str:
        return digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "mode": self.mode,
            "seed": self.seed,
            "parameters": self.parameters,
            "assignments": self.assignments,
        }

    def select(self, rows: list[dict[str, Any]], partition: str) -> list[dict[str, Any]]:
        return [row for row in rows if self.assignments.get(row["identity"]) == partition]


def validate_fractions(train: float, validation: float) -> None:
    if not 0 < train < 1 or not 0 < validation < 1 or train + validation >= 1:
        raise ValueError("Train and validation fractions must leave a positive test fraction")


def forward_split(
    rows: list[dict[str, Any]], train: float = 0.6, validation: float = 0.2, seed: int = 0
) -> SplitManifest:
    validate_fractions(train, validation)
    grouped: dict[tuple[str, str, str], list[list[dict[str, Any]]]] = defaultdict(list)
    for unit in units(rows):
        grouped[domain(unit[0])].append(unit)
    assignments = {}
    excluded = 0
    for values in grouped.values():
        if len(values) < 5:
            for unit in values:
                for row in unit:
                    assignments[row["identity"]] = "excluded"
                    excluded += 1
            continue
        train_end = max(1, int(len(values) * train))
        validation_end = max(train_end + 1, int(len(values) * (train + validation)))
        validation_end = min(validation_end, len(values) - 1)
        for index, unit in enumerate(values):
            partition = (
                "train" if index < train_end else "validation" if index < validation_end else "test"
            )
            for row in unit:
                assignments[row["identity"]] = partition
    manifest = SplitManifest(
        assignments,
        "forward",
        seed,
        {
            "train_fraction": train,
            "validation_fraction": validation,
            "unit": "whole session or timestamp tie",
            "excluded_rows": excluded,
            "chronology": "within known source/learner/order domain only",
        },
    )
    audit_split(rows, manifest)
    return manifest


def learner_split(
    rows: list[dict[str, Any]], train: float = 0.6, validation: float = 0.2, seed: int = 0
) -> SplitManifest:
    validate_fractions(train, validation)
    learners = sorted({(row["source_namespace"], row["learner_id"]) for row in rows})
    if len(learners) < 5:
        raise ValueError("Learner-held-out evaluation requires at least five learners")
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(learners))
    train_end = max(1, int(len(learners) * train))
    validation_end = min(
        len(learners) - 1, max(train_end + 1, int(len(learners) * (train + validation)))
    )
    learner_partitions = {}
    for index, position in enumerate(order):
        learner_partitions[learners[position]] = (
            "train" if index < train_end else "validation" if index < validation_end else "test"
        )
    assignments = {
        row["identity"]: learner_partitions[(row["source_namespace"], row["learner_id"])]
        for row in rows
    }
    manifest = SplitManifest(
        assignments,
        "learner",
        seed,
        {"train_fraction": train, "validation_fraction": validation, "unit": "whole learner"},
    )
    audit_split(rows, manifest)
    return manifest


def rolling_splits(
    rows: list[dict[str, Any]], folds: int = 3, seed: int = 0
) -> list[SplitManifest]:
    if not 2 <= folds <= 10:
        raise ValueError("Rolling folds must be between 2 and 10")
    grouped: dict[tuple[str, str, str], list[list[dict[str, Any]]]] = defaultdict(list)
    for unit in units(rows):
        grouped[domain(unit[0])].append(unit)
    result = []
    for fold in range(folds):
        assignments = {}
        for values in grouped.values():
            n = len(values)
            if n < folds + 4:
                for unit in values:
                    for row in unit:
                        assignments[row["identity"]] = "excluded"
                continue
            train_end = max(1, int(n * (0.35 + 0.35 * fold / folds)))
            validation_end = max(train_end + 1, int(n * (0.45 + 0.35 * fold / folds)))
            test_end = min(n, max(validation_end + 1, int(n * (0.55 + 0.35 * fold / folds))))
            for index, unit in enumerate(values):
                part = (
                    "train"
                    if index < train_end
                    else "validation"
                    if index < validation_end
                    else "test"
                    if index < test_end
                    else "excluded"
                )
                for row in unit:
                    assignments[row["identity"]] = part
        manifest = SplitManifest(assignments, "rolling", seed, {"fold": fold, "folds": folds})
        audit_split(rows, manifest)
        result.append(manifest)
    return result


def audit_split(rows: list[dict[str, Any]], manifest: SplitManifest) -> dict[str, Any]:
    identities = [row["identity"] for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate canonical identities in evaluation data")
    if set(identities) != set(manifest.assignments):
        raise ValueError("Split manifest does not exactly cover input rows")
    ranks = {"train": 0, "validation": 1, "test": 2, "excluded": 3}
    previous: dict[tuple[str, str, str], int] = {}
    for unit in units(rows):
        partitions = {manifest.assignments[row["identity"]] for row in unit}
        if len(partitions) != 1:
            raise ValueError("Session or timestamp tie crosses a split boundary")
        partition = partitions.pop()
        if partition not in ranks:
            raise ValueError("Unknown split partition")
        if manifest.mode in {"forward", "rolling"} and partition != "excluded":
            key = domain(unit[0])
            rank = ranks[partition]
            if rank < previous.get(key, -1):
                raise ValueError("A future unit enters an earlier training partition")
            previous[key] = rank
    if manifest.mode == "learner":
        learner_parts: dict[tuple[str, str], set[str]] = defaultdict(set)
        for row in rows:
            learner_parts[(row["source_namespace"], row["learner_id"])].add(
                manifest.assignments[row["identity"]]
            )
        if any(len(value) != 1 for value in learner_parts.values()):
            raise ValueError("Learner-held-out split shares a learner across partitions")
    counts = {name: sum(value == name for value in manifest.assignments.values()) for name in ranks}
    return {"valid": True, "counts": counts, "split_hash": manifest.hash}
