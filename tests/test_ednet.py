import csv
import io
import zipfile

from metricon.ingest.ednet import create_subset
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.pipeline import preview


def zipped_csv(path, name, rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, buffer.getvalue())


def test_authored_ednet_structure_metadata_join(tmp_path):
    contents = tmp_path / "content.zip"
    zipped_csv(
        contents,
        "contents/questions.csv",
        [
            {
                "question_id": "q1",
                "bundle_id": "b1",
                "correct_answer": "b",
                "part": "1",
                "tags": "1;2;-1",
                "explanation_id": "e1",
                "deployed_at": "0",
            }
        ],
    )
    kt1 = tmp_path / "kt1.zip"
    zipped_csv(
        kt1,
        "KT1/u1.csv",
        [
            {
                "timestamp": str(1500000000000 + index * 1000),
                "solving_id": str(index),
                "question_id": "q1",
                "user_answer": "b" if index % 2 else "a",
                "elapsed_time": "60000",
            }
            for index in range(6)
        ],
    )
    target = tmp_path / "subset.ndjson"
    manifest = create_subset(kt1, contents, target, minimum_interactions=6, minimum_learners=1)
    assert manifest["interactions"] == 6 and manifest["learners"] == 1
    sample = preview(target, AdapterOptions("ndjson", "ednet-kt1"))
    assert sample["events"][0]["correct"] is False
    assert sample["events"][1]["correct"] is True
    assert sample["events"][0]["skills"] == ["ednet:1", "ednet:2"]
    assert sample["events"][0]["time_semantics"] == "shifted"
    assert sample["events"][0]["duration_scope"] == "bundle"
