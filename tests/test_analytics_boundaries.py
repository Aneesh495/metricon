import json

import pytest

from conftest import event
from metricon.analytics.engine import Analytics
from metricon.analytics.sessions import sessions
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.pipeline import import_file
from metricon.quality.audit import dataset_audit


def imported(catalog, tmp_path, rows):
    source = tmp_path / "analytics.ndjson"
    source.write_text("\n".join(json.dumps(row.model_dump(mode="json")) for row in rows))
    workspace = catalog.create_workspace("analytical boundaries")
    return import_file(catalog, workspace["id"], source, AdapterOptions("ndjson", "test"))[
        "dataset_id"
    ]


def test_mixed_duration_scopes_preserve_one_bundle_and_each_event(catalog, tmp_path):
    values = [
        event(
            0, session_id="session", bundle_id="bundle", duration_ms=1000, duration_scope="event"
        ),
        event(
            1, session_id="session", bundle_id="bundle", duration_ms=5000, duration_scope="bundle"
        ),
        event(
            2, session_id="session", bundle_id="bundle", duration_ms=5000, duration_scope="bundle"
        ),
        event(3, duration_ms=9000, duration_scope="unknown"),
        event(4, duration_ms=0, duration_scope="event"),
    ]
    dataset = imported(catalog, tmp_path, values)
    duration = Analytics(catalog, dataset).overview()["durations"]
    assert duration["n"] == 3
    assert duration["total_ms"] == 6000
    assert duration["median_ms"] == 1000
    session = sessions(catalog, dataset)["rows"][0]
    assert session["known_duration_ms"] == 6000
    assert session["duration_observations"] == 2


def test_all_incorrect_history_has_zero_streak_and_unknown_empty_group(catalog, tmp_path):
    dataset = imported(catalog, tmp_path, [event(i, correct=False) for i in range(4)])
    analytics = Analytics(catalog, dataset)
    assert analytics.streaks("u1")["domains"][0]["longest_correct_streak"] == 0
    empty = analytics.overview("unknown")
    assert empty["accuracy"]["n"] == 0 and empty["accuracy"]["estimate"] is None


def test_analytical_cache_is_parameter_scoped_and_checks_payload(catalog, tmp_path):
    dataset = imported(catalog, tmp_path, [event(i) for i in range(4)])
    analytics = Analytics(catalog, dataset)
    first = analytics.cached_overview({"learner_id": None})
    assert analytics.cached_overview({"learner_id": None})["artifact_id"] == first["artifact_id"]
    other = analytics.cached_overview({"learner_id": "u1"})
    assert other["artifact_id"] != first["artifact_id"]
    (catalog.root / "artifacts" / first["artifact_id"] / "overview.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        analytics.cached_overview({"learner_id": None})


def test_source_manifest_tampering_is_detected(catalog, tmp_path):
    dataset = imported(catalog, tmp_path, [event(0)])
    assert dataset_audit(catalog, dataset, True)["valid"]
    (catalog.root / "datasets" / dataset / "manifest.json").write_text("{}")
    assert not dataset_audit(catalog, dataset, True)["valid"]
