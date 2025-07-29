from __future__ import annotations

import csv
import json
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from metricon.schema.events import ARROW_SCHEMA, event_from_row
from metricon.storage.artifacts import ArtifactWriter
from metricon.storage.catalog import Catalog
from metricon.storage.query import analytical_connection

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
CSV_ENCODING = "spreadsheet-literal-v1"


def csv_literal(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def export_dataset(
    catalog: Catalog, dataset_id: str, format: str = "json", learner_id: str | None = None
) -> str:
    if format not in {"json", "csv", "parquet", "ndjson"}:
        raise ValueError("Unsupported canonical export format")
    catalog.dataset(dataset_id)
    filename = f"events.{format}"
    count = 0
    with (
        ArtifactWriter(catalog, "export", dataset_id) as writer,
        analytical_connection(catalog, dataset_id) as connection,
    ):
        condition, parameters = (" WHERE learner_id=?", [learner_id]) if learner_id else ("", [])
        reader = connection.execute(
            "SELECT * FROM events"
            + condition
            + " ORDER BY source_namespace,learner_id,source_sequence,event_id",
            parameters,
        ).fetch_record_batch(8192)
        path = writer.path / filename
        if format == "parquet":
            with pq.ParquetWriter(path, ARROW_SCHEMA, compression="zstd") as parquet:
                for batch in reader:
                    table = pa.Table.from_batches([batch]).cast(ARROW_SCHEMA)
                    parquet.write_table(table)
                    count += len(batch)
        else:
            with path.open("w", encoding="utf-8", newline="") as output:
                csv_writer = None
                if format == "json":
                    output.write("[\n")
                for batch in reader:
                    for row in batch.to_pylist():
                        payload = event_from_row(row).model_dump(mode="json")
                        if format == "csv":
                            payload["csv_encoding"] = CSV_ENCODING
                            payload["skills"] = json.dumps(payload["skills"], ensure_ascii=False)
                            payload["provenance"] = json.dumps(
                                payload["provenance"], ensure_ascii=False
                            )
                            payload["correct"] = "true" if payload["correct"] else "false"
                            payload = {key: csv_literal(value) for key, value in payload.items()}
                            if csv_writer is None:
                                csv_writer = csv.DictWriter(output, fieldnames=payload.keys())
                                csv_writer.writeheader()
                            csv_writer.writerow(payload)
                        else:
                            if format == "json" and count:
                                output.write(",\n")
                            output.write(json.dumps(payload, ensure_ascii=False, allow_nan=False))
                            if format == "ndjson":
                                output.write("\n")
                        count += 1
                if format == "json":
                    output.write("\n]\n")
        return writer.publish(
            {
                "dataset_id": dataset_id,
                "format": format,
                "filename": filename,
                "rows": count,
                "learner_id": learner_id,
                "schema_version": "attempt/1",
                "csv_encoding": CSV_ENCODING if format == "csv" else None,
                "meaning": "Accepted canonical events at this exact dataset version; quarantine records are excluded",
            }
        )
