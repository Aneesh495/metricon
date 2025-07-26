import json

import pytest

from conftest import event
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.pipeline import import_file, preview, reconcile
from metricon.schema.events import AttemptEvent
from metricon.storage.query import scan_events


def source(tmp_path, values, name="events.ndjson"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(value) for value in values) + "\n")
    return path


def payload(index=0, **changes):
    value = event(index).model_dump(mode="json", exclude={"provenance"})
    value.update(changes)
    return value


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None, [], {}])
def test_boolean_is_not_truthiness(value):
    with pytest.raises(ValueError):
        AttemptEvent.model_validate({**event().model_dump(), "correct": value})


def test_legacy_unicode_and_no_invented_dates(catalog, tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "LocalSubmissions": {
                    "中文.ε": {
                        "attempts": [
                            {"id": "a", "correct": False, "type": "MULTIPLE_CHOICE"},
                            {"id": "b", "correct": True},
                        ]
                    }
                }
            },
            ensure_ascii=False,
        )
    )
    result = preview(path, AdapterOptions("legacy", "test"))
    assert len(result["events"]) == 2
    assert all(row["timestamp"] is None and row["duration_ms"] is None for row in result["events"])
    assert all(row["order_scope"] == "question" for row in result["events"])
    assert result["events"][0]["question_id"] == "中文.ε"


def test_duplicate_conflict_and_repeated_attempt(catalog, tmp_path):
    workspace = catalog.create_workspace("user")
    options = AdapterOptions("ndjson", "test")
    path = source(tmp_path, [payload()])
    first = import_file(catalog, workspace["id"], path, options)
    second = import_file(catalog, workspace["id"], path, options)
    assert second["duplicate_import"]
    path = source(tmp_path, [payload(), payload(0, correct=False), payload(1)], "changed.ndjson")
    result = import_file(catalog, workspace["id"], path, options)
    assert result["report"]["accepted"] == 1
    assert result["report"]["conflicts"] == 1
    assert result["report"]["duplicates"] == 1
    assert result["report"]["balanced"]
    assert len(scan_events(catalog, result["dataset_id"]).collect()) == 2
    assert catalog.dataset(first["dataset_id"])["row_count"] == 1
    path = source(tmp_path, [payload(), payload(1)], "equivalent.ndjson")
    equivalent = import_file(catalog, workspace["id"], path, options)
    assert equivalent["dataset_id"] == result["dataset_id"]
    assert equivalent["report"]["accepted"] == 0


@pytest.mark.parametrize(
    "phase", ["after_partitions", "before_rename", "after_rename", "before_commit"]
)
def test_crash_preserves_old_manifest(catalog, tmp_path, phase):
    workspace = catalog.create_workspace("user")
    options = AdapterOptions("ndjson", "test")
    first = import_file(catalog, workspace["id"], source(tmp_path, [payload()]), options)

    def fault(current):
        if current == phase:
            raise RuntimeError("injected crash")

    with pytest.raises(RuntimeError):
        import_file(
            catalog,
            workspace["id"],
            source(tmp_path, [payload(1)], "next.ndjson"),
            options,
            fault=fault,
        )
    assert catalog.workspace(workspace["id"])["dataset_id"] == first["dataset_id"]
    reconcile(catalog)
    result = import_file(catalog, workspace["id"], tmp_path / "next.ndjson", options)
    assert catalog.dataset(result["dataset_id"])["row_count"] == 2
    assert not list((catalog.root / "staging").glob("*"))


def test_malformed_lines_bounded_quarantine(catalog, tmp_path):
    path = tmp_path / "broken.ndjson"
    path.write_bytes((b"{bad}\n" * 100) + b'"false"\n' + json.dumps(payload()).encode() + b"\n")
    workspace = catalog.create_workspace("user")
    result = import_file(
        catalog, workspace["id"], path, AdapterOptions("ndjson", "test"), chunk_size=1
    )
    assert result["report"]["rejected"] == 101
    assert len(result["report"]["samples"]) == 50
    assert result["report"]["accepted"] == 1


def test_csv_quotes_and_boolean(catalog, tmp_path):
    import csv

    value = payload()
    value.pop("schema_version")
    value["skills"] = json.dumps(["s,1", "ε"])
    value["question_id"] = "quoted,question"
    value["correct"] = "false"
    path = tmp_path / "events.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=value.keys())
        writer.writeheader()
        writer.writerow(value)
    result = preview(path, AdapterOptions("csv", "test"))
    assert result["events"][0]["correct"] is False
    assert result["events"][0]["question_id"] == "quoted,question"


def test_blank_workspace_is_empty(catalog):
    workspace = catalog.create_workspace("new")
    assert workspace["dataset_id"] is None
    assert catalog.datasets(workspace["id"]) == []
