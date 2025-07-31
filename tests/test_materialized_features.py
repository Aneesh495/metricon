import json

import pyarrow.parquet as pq

from conftest import event
from metricon.features.history import HistoryFeatures
from metricon.features.materialize import materialize_history
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.pipeline import import_file
from metricon.storage.query import scan_events


def test_columnar_features_close_overlapping_sessions_and_cross_session_ties(catalog, tmp_path):
    values = [
        event(i, correct=i % 2 == 0, session_id=["a", "b", "a", "c", "d"][i])
        for i in range(5)
    ]
    values[3] = values[3].model_copy(update={"timestamp": values[2].timestamp})
    source = tmp_path / "coupled.ndjson"
    source.write_text("\n".join(json.dumps(v.model_dump(mode="json")) for v in values) + "\n")
    workspace = catalog.create_workspace("coupled")
    imported = import_file(catalog, workspace["id"], source, AdapterOptions("ndjson", "test"))
    rows = scan_events(catalog, imported["dataset_id"]).collect().to_dicts()
    features, ordered = HistoryFeatures().transform(rows)
    output = tmp_path / "features.parquet"
    result = materialize_history(catalog, imported["dataset_id"], output, chunk_size=2)
    actual = {row["identity"]: row for row in pq.read_table(output).to_pylist()}
    assert result["rows"] == 5
    assert [actual[row["identity"]]["past_attempts"] for row in ordered] == [0, 0, 0, 0, 4]
    for row, feature in zip(ordered, features):
        assert actual[row["identity"]]["past_accuracy"] == feature["learner_rate"]
        assert actual[row["identity"]]["item_past_accuracy"] == feature["item_rate"]


def test_unknown_time_stream_has_independent_sequence_events(catalog, tmp_path):
    values = [event(i, timestamp=None, time_semantics="unknown") for i in range(6)]
    source = tmp_path / "unknown.ndjson"
    source.write_text("\n".join(json.dumps(v.model_dump(mode="json")) for v in values) + "\n")
    workspace = catalog.create_workspace("unknown")
    imported = import_file(catalog, workspace["id"], source, AdapterOptions("ndjson", "test"))
    output = tmp_path / "features.parquet"
    materialize_history(catalog, imported["dataset_id"], output, chunk_size=2)
    assert [r["past_attempts"] for r in pq.read_table(output).to_pylist()] == list(range(6))
