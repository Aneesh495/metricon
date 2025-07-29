from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json, file_hash
from metricon.storage.query import analytical_connection

FEATURE_SCHEMA = pa.schema(
    [
        ("identity", pa.string()),
        ("learner_id", pa.string()),
        ("question_id", pa.string()),
        ("correct", pa.bool_()),
        ("past_attempts", pa.int64()),
        ("past_successes", pa.int64()),
        ("past_accuracy", pa.float64()),
        ("recent_accuracy", pa.float64()),
        ("item_past_attempts", pa.int64()),
        ("item_past_accuracy", pa.float64()),
    ]
)


def materialize_history(
    catalog: Catalog, dataset_id: str, destination: Path, chunk_size: int = 8192
) -> dict[str, Any]:
    if not 1 <= chunk_size <= 65536:
        raise ValueError("Invalid feature chunk size")
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    batch = []
    learner_key = None
    attempts = successes = 0
    recent: deque[int] = deque(maxlen=10)
    item_counts: dict[str, list[int]] = {}
    pending: list[dict[str, Any]] = []
    unit_key = None

    def flush_unit(writer: pq.ParquetWriter) -> None:
        nonlocal attempts, successes, rows_written
        for row in pending:
            count, correct = item_counts.get(row["question_id"], [0, 0])
            batch.append(
                {
                    "identity": row["identity"],
                    "learner_id": row["learner_id"],
                    "question_id": row["question_id"],
                    "correct": row["correct"],
                    "past_attempts": attempts,
                    "past_successes": successes,
                    "past_accuracy": (successes + 1) / (attempts + 2),
                    "recent_accuracy": (sum(recent) + 1) / (len(recent) + 2),
                    "item_past_attempts": count,
                    "item_past_accuracy": (correct + 1) / (count + 2),
                }
            )
        for row in pending:
            attempts += 1
            successes += int(row["correct"])
            recent.append(int(row["correct"]))
            counts = item_counts.setdefault(row["question_id"], [0, 0])
            counts[0] += 1
            counts[1] += int(row["correct"])
        pending.clear()
        if len(batch) >= chunk_size:
            writer.write_table(pa.Table.from_pylist(batch, schema=FEATURE_SCHEMA))
            rows_written += len(batch)
            batch.clear()

    with (
        analytical_connection(catalog, dataset_id) as connection,
        pq.ParquetWriter(destination, FEATURE_SCHEMA, compression="zstd") as writer,
    ):
        reader = connection.execute("""SELECT identity,source_namespace,learner_id,question_id,correct,order_scope,source_sequence,
            session_id,timestamp FROM events ORDER BY source_namespace,learner_id,
            CASE WHEN order_scope='question' THEN question_id ELSE '' END,
            timestamp NULLS LAST,source_sequence,event_id""").fetch_record_batch(chunk_size)
        for arrow_batch in reader:
            for row in arrow_batch.to_pylist():
                key = (
                    row["source_namespace"],
                    row["learner_id"],
                    row["question_id"] if row["order_scope"] == "question" else "",
                )
                current_unit = (
                    key,
                    row["session_id"] or row["timestamp"] or row["source_sequence"],
                )
                if current_unit != unit_key or len(pending) >= 65536:
                    if len(pending) >= 65536:
                        raise ValueError(
                            "Coupled feature unit exceeds the bounded materialization limit"
                        )
                    flush_unit(writer)
                    if key != learner_key:
                        attempts = successes = 0
                        recent.clear()
                        item_counts.clear()
                    learner_key, unit_key = key, current_unit
                pending.append(row)
        flush_unit(writer)
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=FEATURE_SCHEMA))
            rows_written += len(batch)
    manifest = {
        "version": "materialized-history/1",
        "dataset_id": dataset_id,
        "rows": rows_written,
        "sha256": file_hash(destination),
        "bytes": destination.stat().st_size,
        "semantics": "Pre-unit features; label stored separately; question-local legacy domains",
        "restriction": "Input sessions must be contiguous in chronological order; packaged experiment units handle overlapping sessions",
    }
    atomic_json(destination.with_suffix(".manifest.json"), manifest)
    return manifest
