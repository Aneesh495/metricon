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
        coupled = connection.execute(
            "SELECT count(*) FROM events WHERE session_id IS NOT NULL OR timestamp IS NOT NULL"
        ).fetchone()[0]
        base = """SELECT identity,source_namespace,learner_id,question_id,correct,order_scope,
            source_sequence,session_id,timestamp,event_id,
            CASE WHEN order_scope='question' THEN question_id ELSE '' END ordering_domain
            FROM events"""
        if coupled:
            # Interval closure keeps noncontiguous sessions and cross-session ties atomic.
            # Window computations spill through DuckDB's bounded analytical connection.
            sql = f"""WITH numbered AS (
                SELECT *,row_number() OVER(PARTITION BY source_namespace,learner_id,ordering_domain
                    ORDER BY timestamp NULLS LAST,source_sequence,event_id) sequence_position FROM ({base})
            ), endings AS (
                SELECT *,greatest(
                    max(sequence_position) OVER(PARTITION BY source_namespace,learner_id,ordering_domain,
                        CASE WHEN session_id IS NOT NULL THEN 's:'||session_id
                             WHEN timestamp IS NOT NULL THEN 't:'||timestamp::VARCHAR
                             ELSE 'e:'||event_id END),
                    CASE WHEN timestamp IS NOT NULL THEN max(sequence_position) OVER(
                        PARTITION BY source_namespace,learner_id,ordering_domain,timestamp)
                        ELSE sequence_position END) unit_end FROM numbered
            ), boundaries AS (
                SELECT *,CASE WHEN sequence_position > coalesce(max(unit_end) OVER(
                    PARTITION BY source_namespace,learner_id,ordering_domain ORDER BY sequence_position
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),0)
                    THEN 1 ELSE 0 END boundary FROM endings
            ) SELECT *,sum(boundary) OVER(PARTITION BY source_namespace,learner_id,ordering_domain
                ORDER BY sequence_position ROWS UNBOUNDED PRECEDING) unit_number FROM boundaries
                ORDER BY source_namespace,learner_id,ordering_domain,sequence_position"""
        else:
            sql = f"""SELECT *,event_id unit_number FROM ({base})
                ORDER BY source_namespace,learner_id,ordering_domain,source_sequence,event_id"""
        reader = connection.execute(sql).fetch_record_batch(chunk_size)
        for arrow_batch in reader:
            for row in arrow_batch.to_pylist():
                key = (
                    row["source_namespace"],
                    row["learner_id"],
                    row["question_id"] if row["order_scope"] == "question" else "",
                )
                current_unit = (
                    key,
                    row["unit_number"],
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
        "version": "materialized-history/2",
        "dataset_id": dataset_id,
        "rows": rows_written,
        "sha256": file_hash(destination),
        "bytes": destination.stat().st_size,
        "semantics": "Pre-unit features; label stored separately; question-local legacy domains",
        "restriction": "Coupled units are bounded at 65536 observations; larger units fail explicitly",
        "coupling": "Whole source sessions, timestamp ties and their transitive interval closure",
    }
    atomic_json(destination.with_suffix(".manifest.json"), manifest)
    return manifest
