import json

import pytest

from conftest import event
from metricon.ingest.adapters import AdapterOptions, records
from metricon.ingest.pipeline import import_file


def test_json_framing_bounds_nested_and_escaped_items(tmp_path):
    path = tmp_path / "array.json"
    path.write_text(
        json.dumps(
            [
                {"text": 'nested , ] } \\"', "child": [{"value": 3}]},
                {"text": "x" * 1000},
                {"after": True},
            ]
        )
    )
    parsed = list(records(path, AdapterOptions("json", max_event_bytes=200)))
    assert len(parsed) == 3
    assert parsed[0].value["child"][0]["value"] == 3
    assert parsed[1].error == "Canonical JSON event exceeds configured byte bound"
    assert parsed[2].value == {"after": True}
    path.write_text("[" + " " * 1000 + "]")
    assert list(records(path, AdapterOptions("json", max_event_bytes=100))) == []


@pytest.mark.parametrize("value", ['{"wrong":1}', "[{},]", "[{},", "[{}] trailing", '[{"x":}]'])
def test_structurally_malformed_json_never_advances_pointer(catalog, tmp_path, value):
    workspace = catalog.create_workspace("malformed")
    path = tmp_path / "malformed.json"
    path.write_text(value)
    with pytest.raises(ValueError):
        import_file(catalog, workspace["id"], path, AdapterOptions("json"), chunk_size=1)
    assert catalog.workspace(workspace["id"])["dataset_id"] is None
    assert list((catalog.root / "staging").iterdir()) == []


def test_columnar_sequence_bound_rejects_only_the_invalid_record(catalog, tmp_path):
    values = [event(0).model_dump(mode="json"), event(1).model_dump(mode="json")]
    values[1]["source_sequence"] = 2**63
    path = tmp_path / "bound.ndjson"
    path.write_text("\n".join(json.dumps(row) for row in values))
    workspace = catalog.create_workspace("bounded")
    result = import_file(catalog, workspace["id"], path, AdapterOptions("ndjson", "test"))
    assert result["report"]["accepted"] == result["report"]["rejected"] == 1
