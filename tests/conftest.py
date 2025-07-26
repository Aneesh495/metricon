from datetime import datetime, timedelta, timezone

import pytest

from metricon.schema.events import AttemptEvent, Provenance
from metricon.storage.catalog import Catalog


@pytest.fixture
def catalog(tmp_path):
    return Catalog(tmp_path / "storage")


def event(index=0, learner="u1", question="q1", correct=True, **changes):
    payload = {
        "source_namespace": "test",
        "event_id": str(index),
        "learner_id": learner,
        "question_id": question,
        "skills": ["s1"],
        "correct": correct,
        "source_sequence": index,
        "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index),
        "time_semantics": "real",
        "provenance": Provenance(source_hash="fixture", adapter="fixture", row=index),
    }
    payload.update(changes)
    return AttemptEvent(**payload)


@pytest.fixture
def rows():
    return [
        event(
            index=index,
            learner=f"u{learner}",
            question=f"q{index % 4}",
            correct=(index + learner) % 3 != 0,
            event_id=f"{learner}:{index}",
            session_id=f"session-{index // 2}",
        ).arrow_row()
        for learner in range(25)
        for index in range(30)
    ]
