from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from metricon.storage.hashing import atomic_json, file_hash

WORKLOAD_VERSION = "stream-corpus/1"


def workload_record(index: int) -> dict[str, Any]:
    position = index % 1000
    target = index - (position - 996) if position in {997, 998} else index
    correct: Any = target % 3 != 0
    if position == 998:
        correct = not correct
    if position == 999:
        correct = "false"
    return {
        "source_namespace": "scale-synthetic",
        "event_id": str(target),
        "learner_id": f"learner-{target % 10000}",
        "question_id": f"question-{target % 200}",
        "skills": [f"skill-{target % 10}"],
        "correct": correct,
        "source_sequence": target,
        "duration_ms": 60000,
        "duration_scope": "event",
        "attempt_kind": "practice",
    }


def workload_reference(rows: int) -> dict[str, int]:
    if rows < 1:
        raise ValueError("A streaming workload requires at least one row")
    blocks, remainder = divmod(rows, 1000)
    counts = {
        "received": rows,
        "duplicates": blocks + int(remainder > 997),
        "conflicts": blocks + int(remainder > 998),
        "rejected": blocks + int(remainder > 999),
    }
    counts["accepted"] = rows - counts["duplicates"] - counts["conflicts"] - counts["rejected"]
    return counts


def write_workload(path: Path, rows: int) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = path.with_suffix(".manifest.json")
    if path.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if (
            manifest["rows"] == rows
            and manifest["version"] == WORKLOAD_VERSION
            and file_hash(path) == manifest["sha256"]
        ):
            return manifest
        raise ValueError("An existing workload does not match its immutable manifest")
    with path.open("w", buffering=1024 * 1024) as handle:
        for index in range(rows):
            handle.write(json.dumps(workload_record(index), separators=(",", ":")) + "\n")
    manifest = {
        "version": WORKLOAD_VERSION,
        "rows": rows,
        "sha256": file_hash(path),
        "bytes": path.stat().st_size,
        "reference_counts": workload_reference(rows),
        "identity_policy": "Every block has one duplicate and one conflict of index 996, then a strict-boolean rejection",
        "synthetic": True,
    }
    atomic_json(manifest_path, manifest)
    return manifest


def accepted_indexes(rows: int) -> Iterator[int]:
    return (index for index in range(rows) if index % 1000 < 997)


def reference_checksum(rows: int) -> dict[str, int]:
    accepted = list(range(min(rows, 1000)))
    del accepted[997:]
    blocks, remainder = divmod(rows, 1000)
    count = blocks * 997 + min(remainder, 997)
    total = 997 * 1000 * blocks * (blocks - 1) // 2 + sum(range(997)) * blocks
    total += min(remainder, 997) * blocks * 1000 + sum(range(min(remainder, 997)))
    successes = sum(index % 3 != 0 for index in accepted_indexes(rows))
    return {"n": count, "index_sum": total, "successes": successes}
