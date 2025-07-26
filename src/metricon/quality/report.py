from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from metricon.schema.events import AttemptEvent


@dataclass
class QualityReport:
    sample_limit: int = 50
    received: int = 0
    accepted: int = 0
    duplicates: int = 0
    conflicts: int = 0
    rejected: int = 0
    counters: Counter[str] = field(default_factory=Counter)
    samples: list[dict[str, Any]] = field(default_factory=list)

    def observation(self, event: AttemptEvent) -> None:
        if event.timestamp is None:
            self.counters["unknown_timestamp"] += 1
        if event.duration_ms is None:
            self.counters["unknown_duration"] += 1
        if not event.skills:
            self.counters["unknown_skills"] += 1
        if event.order_scope == "question":
            self.counters["question_only_order"] += 1
        if event.time_semantics == "shifted":
            self.counters["shifted_time"] += 1
        if event.duration_scope == "bundle":
            self.counters["bundle_duration"] += 1
        if event.provenance.identity_quality == "position_only":
            self.counters["position_only_identity"] += 1

    def problem(
        self, category: str, row: int, reason: str, identity: str | None = None
    ) -> dict[str, Any]:
        value = {"category": category, "row": row, "reason": reason[:2000], "identity": identity}
        if len(self.samples) < self.sample_limit:
            self.samples.append(value)
        return value

    def as_dict(self) -> dict[str, Any]:
        warnings = []
        definitions = {
            "unknown_timestamp": "Elapsed-time trends are unavailable for observations without timestamps.",
            "unknown_duration": "Unknown durations are excluded from duration statistics and timed planning.",
            "unknown_skills": "Untagged items are evaluated separately; a question ID is not a skill label.",
            "question_only_order": "Only per-question order is known. Global learner chronology is unavailable.",
            "shifted_time": "Source timestamps are shifted; calendar interpretation is unsupported.",
            "bundle_duration": "Bundle duration must be counted once per learner/session, not once per answer.",
            "position_only_identity": "Legacy positional identities cannot reliably match reordered or deleted attempts.",
        }
        for code, count in sorted(self.counters.items()):
            warnings.append({"code": code, "count": count, "message": definitions[code]})
        return {
            "received": self.received,
            "accepted": self.accepted,
            "duplicates": self.duplicates,
            "conflicts": self.conflicts,
            "rejected": self.rejected,
            "warnings": warnings,
            "samples": self.samples,
            "sample_limit": self.sample_limit,
            "balanced": self.received
            == self.accepted + self.duplicates + self.conflicts + self.rejected,
        }
