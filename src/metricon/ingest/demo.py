from __future__ import annotations

import uuid

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.pipeline import import_file
from metricon.models.bkt import BKTParameters
from metricon.schema.events import canonical_json
from metricon.storage.catalog import Catalog


def demo_workspace(
    catalog: Catalog, seed: int = 2026, learners: int = 50, attempts: int = 60
) -> dict[str, Any]:
    if not 1 <= learners <= 1000 or not 1 <= attempts <= 1000:
        raise ValueError("Invalid demonstration bounds")
    workspace = catalog.create_workspace("Synthetic research sandbox", "synthetic")
    temporary = catalog.root / f"demo-source-{uuid.uuid4().hex}.ndjson"
    rng = np.random.default_rng(seed)
    skills = ["algebra", "logic", "probability"]
    parameters = BKTParameters()
    with temporary.open("w", encoding="utf-8") as handle:
        for learner in range(learners):
            known = {skill: bool(rng.random() < parameters.initial) for skill in skills}
            for sequence in range(attempts):
                skill = skills[sequence % len(skills)]
                probability = 1 - parameters.slip if known[skill] else parameters.guess
                correct = bool(rng.random() < probability)
                if not known[skill] and rng.random() < parameters.learning:
                    known[skill] = True
                timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
                    minutes=sequence * 3
                )
                row = {
                    "source_namespace": f"synthetic-{seed}",
                    "event_id": f"{learner}:{sequence}",
                    "learner_id": f"demo-{learner:03d}",
                    "question_id": f"{skill}-{sequence % 10}",
                    "skills": [skill],
                    "correct": correct,
                    "attempt_kind": "practice",
                    "source_sequence": sequence,
                    "timestamp": timestamp.isoformat(),
                    "duration_ms": int(rng.integers(20000, 120000)),
                    "duration_scope": "event",
                    "session_id": f"session-{sequence // 3}",
                    "time_semantics": "real",
                }
                handle.write(canonical_json(row) + "\n")
    result = import_file(
        catalog, workspace["id"], temporary, AdapterOptions("ndjson", f"synthetic-{seed}")
    )
    temporary.unlink(missing_ok=True)
    return {
        "workspace": catalog.workspace(workspace["id"]),
        "import": result,
        "synthetic": True,
        "seed": seed,
        "generator": "Binary BKT demonstration; no public-data research claim",
    }
