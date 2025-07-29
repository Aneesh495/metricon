import json

import pytest

from conftest import event
from metricon.analytics.exports import export_dataset
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.pipeline import import_file
from metricon.quality.drift import DriftConfig, window_diagnostics
from metricon.storage.query import scan_events


@pytest.mark.parametrize("format", ["json", "csv", "ndjson", "parquet"])
def test_export_preserves_canonical_content_and_literal_identifiers(catalog, tmp_path, format):
    source = tmp_path / "source.ndjson"
    values = [
        event(0, question="=SUM(A1)").model_dump(mode="json", exclude={"provenance"}),
        event(1).model_dump(mode="json", exclude={"provenance"}),
    ]
    source.write_text("\n".join(json.dumps(row) for row in values))
    workspace = catalog.create_workspace("source")
    original = import_file(catalog, workspace["id"], source, AdapterOptions("ndjson", "test"))
    artifact = export_dataset(catalog, original["dataset_id"], format)
    exported = catalog.root / "artifacts" / artifact / f"events.{format}"
    if format == "csv":
        assert "'=SUM(A1)" in exported.read_text()
    target = catalog.create_workspace("target")
    imported = import_file(catalog, target["id"], exported, AdapterOptions(format, "test"))
    assert imported["report"]["accepted"] == 2
    expected = (
        scan_events(catalog, original["dataset_id"])
        .collect()
        .select("identity", "content_hash")
        .sort("identity")
    )
    actual = (
        scan_events(catalog, imported["dataset_id"])
        .collect()
        .select("identity", "content_hash")
        .sort("identity")
    )
    assert actual.equals(expected)


def test_drift_requires_actual_adequate_windows():
    reference = [
        {"correct": True, "question_id": "a", "timestamp": None, "duration_ms": None}
        for _ in range(100)
    ]
    current = [
        {"correct": False, "question_id": "b", "timestamp": None, "duration_ms": 1000}
        for _ in range(100)
    ]
    assert not window_diagnostics(reference[:3], current, DriftConfig())["available"]
    report = window_diagnostics(reference, current, DriftConfig())
    assert report["response"]["alert"]
    assert report["item_coverage"]["alert"]
    assert report["missingness"]["duration_ms"]["alert"]
    assert report["calibration"] is None
