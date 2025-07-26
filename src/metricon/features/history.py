from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Iterator

import numpy as np
from sklearn.feature_extraction import DictVectorizer

from metricon.schema.events import digest

FEATURE_VERSION = "asof/1"


@dataclass
class Counts:
    n: int = 0
    successes: int = 0
    recent: deque[int] = field(default_factory=lambda: deque(maxlen=10))
    last_timestamp: datetime | None = None

    @property
    def rate(self) -> float:
        return (self.successes + 1) / (self.n + 2)

    def update(self, row: dict[str, Any]) -> None:
        outcome = int(row["correct"])
        self.n += 1
        self.successes += outcome
        self.recent.append(outcome)
        if row.get("timestamp") is not None:
            self.last_timestamp = row["timestamp"]


def domain(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        row["source_namespace"],
        row["learner_id"],
        row["question_id"] if row["order_scope"] == "question" else "",
    )


def bundle_key(row: dict[str, Any]) -> tuple[Any, ...]:
    if row.get("session_id") is not None:
        return (*domain(row), "session", row["session_id"])
    if row.get("timestamp") is not None:
        return (*domain(row), "tie", row["timestamp"])
    return (*domain(row), "event", row["event_id"])


def ordered_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = list(rows)
    result.sort(
        key=lambda row: (
            domain(row),
            row.get("timestamp").isoformat() if row.get("timestamp") is not None else "9999",
            row["source_sequence"],
            row["event_id"],
        )
    )
    return result


def units(rows: Iterable[dict[str, Any]]) -> Iterator[list[dict[str, Any]]]:
    sorted_rows = ordered_rows(rows)
    by_domain: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in sorted_rows:
        by_domain[domain(row)].append(row)
    for values in by_domain.values():
        last_position: dict[tuple[Any, ...], int] = {}
        last_tie: dict[Any, int] = {}
        for index, row in enumerate(values):
            last_position[bundle_key(row)] = index
            if row.get("timestamp") is not None:
                last_tie[row["timestamp"]] = index
        index = 0
        while index < len(values):
            end = last_position[bundle_key(values[index])]
            cursor = index
            while cursor <= end:
                row = values[cursor]
                end = max(
                    end, last_position[bundle_key(row)], last_tie.get(row.get("timestamp"), cursor)
                )
                cursor += 1
            yield values[index : end + 1]
            index = end + 1


class HistoryFeatures:
    def __init__(self, skill_tags: bool = True, temporal: bool = True):
        self.skill_tags = skill_tags
        self.temporal = temporal
        self.learners: dict[tuple[str, str, str], Counts] = defaultdict(Counts)
        self.items: dict[tuple[Any, ...], Counts] = defaultdict(Counts)
        self.skills: dict[tuple[Any, ...], Counts] = defaultdict(Counts)

    def before(self, row: dict[str, Any]) -> dict[str, float | str]:
        key = domain(row)
        learner = self.learners[key]
        item = self.items[(*key, row["question_id"])]
        recent = learner.recent
        result: dict[str, float | str] = {
            "learner_log_attempts": math.log1p(learner.n),
            "learner_rate": learner.rate,
            "item_log_attempts": math.log1p(item.n),
            "item_rate": item.rate,
            "recent_rate": (sum(recent) + 1) / (len(recent) + 2),
            "recent_count": float(len(recent)),
            "cold_learner": float(learner.n == 0),
            "cold_item": float(item.n == 0),
            "kind": row["attempt_kind"],
        }
        if self.skill_tags:
            for skill in row["skills"]:
                counts = self.skills[(*key, skill)]
                result[f"skill:{skill}"] = 1.0
                result[f"prior_rate:{skill}"] = counts.rate
                result[f"prior_count:{skill}"] = math.log1p(counts.n)
            result["unknown_skill"] = float(not row["skills"])
        if self.temporal:
            timestamp = row.get("timestamp")
            previous = learner.last_timestamp
            known = timestamp is not None and previous is not None
            result["gap_unknown"] = float(not known)
            result["gap_log_seconds"] = (
                math.log1p(max(0, (timestamp - previous).total_seconds())) if known else 0.0
            )
        return result

    def observe(self, row: dict[str, Any]) -> None:
        key = domain(row)
        self.learners[key].update(row)
        self.items[(*key, row["question_id"])].update(row)
        for skill in row["skills"]:
            self.skills[(*key, skill)].update(row)

    def transform(
        self, rows: Iterable[dict[str, Any]], update: bool = True
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        features = []
        ordered = []
        for unit in units(rows):
            for row in unit:
                features.append(self.before(row))
                ordered.append(row)
            if update:
                for row in unit:
                    self.observe(row)
        return features, ordered

    def snapshot(self) -> dict[str, Any]:
        def export(values: dict[Any, Counts]) -> list[dict[str, Any]]:
            return [
                {
                    "key": list(key),
                    "n": value.n,
                    "successes": value.successes,
                    "recent": list(value.recent),
                    "last_timestamp": value.last_timestamp.isoformat()
                    if value.last_timestamp
                    else None,
                }
                for key, value in sorted(values.items())
            ]

        return {
            "learners": export(self.learners),
            "items": export(self.items),
            "skills": export(self.skills),
        }

    def restore_snapshot(self, payload: dict[str, Any]) -> None:
        for name in ["learners", "items", "skills"]:
            destination = getattr(self, name)
            destination.clear()
            for entry in payload[name]:
                counts = Counts(n=entry["n"], successes=entry["successes"])
                counts.recent.extend(entry["recent"])
                counts.last_timestamp = (
                    datetime.fromisoformat(entry["last_timestamp"])
                    if entry["last_timestamp"]
                    else None
                )
                destination[tuple(entry["key"])] = counts


class FeatureEncoder:
    def __init__(self):
        self.vectorizer = DictVectorizer(sparse=True, sort=True)
        self.fitted = False

    def fit_transform(self, features: list[dict[str, Any]]) -> Any:
        if not features:
            raise ValueError("Cannot fit features on empty training data")
        result = self.vectorizer.fit_transform(features)
        self.fitted = True
        return result

    def transform(self, features: list[dict[str, Any]]) -> Any:
        if not self.fitted:
            raise RuntimeError("Feature vocabulary must be fitted on training only")
        return self.vectorizer.transform(features)

    @property
    def names(self) -> list[str]:
        return list(self.vectorizer.get_feature_names_out())

    def parameters(self) -> dict[str, Any]:
        return {
            "feature_version": FEATURE_VERSION,
            "vocabulary": self.vectorizer.vocabulary_,
            "feature_names": self.names,
            "vocabulary_hash": digest(self.names),
        }

    @classmethod
    def restore(cls, payload: dict[str, Any]) -> FeatureEncoder:
        if payload["feature_version"] != FEATURE_VERSION:
            raise ValueError("Unsupported feature version")
        encoder = cls()
        encoder.vectorizer.vocabulary_ = {
            key: int(value) for key, value in payload["vocabulary"].items()
        }
        encoder.vectorizer.feature_names_ = payload["feature_names"]
        encoder.fitted = True
        return encoder


def labels(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray([int(row["correct"]) for row in rows], dtype=np.int8)
