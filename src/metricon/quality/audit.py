from __future__ import annotations

from typing import Any

from metricon.storage.catalog import Catalog
from metricon.storage.hashing import file_hash
from metricon.storage.query import analytical_connection


def dataset_audit(
    catalog: Catalog, dataset_id: str, verify_checksums: bool = False
) -> dict[str, Any]:
    dataset = catalog.dataset(dataset_id)
    manifest = dataset["manifest"]
    partition_errors = []
    if verify_checksums:
        for partition in manifest["partitions"]:
            path = catalog.root / partition["path"]
            if not path.is_file() or file_hash(path) != partition["sha256"]:
                partition_errors.append(partition["path"])
    with analytical_connection(catalog, dataset_id) as connection:
        row_count, distinct, known, unknown, shifted = connection.execute("""
            SELECT count(*),count(DISTINCT identity),count(timestamp),count(*) FILTER(WHERE timestamp IS NULL),
            count(*) FILTER(WHERE time_semantics='shifted') FROM events
        """).fetchone()
        time_ties = connection.execute("""
            SELECT coalesce(sum(n-1),0) FROM (
                SELECT count(*) n FROM events WHERE timestamp IS NOT NULL
                GROUP BY source_namespace,learner_id,timestamp HAVING count(*)>1)
        """).fetchone()[0]
        inversions = connection.execute("""
            WITH ordered AS (
                SELECT timestamp,lag(timestamp) OVER(PARTITION BY source_namespace,learner_id,
                  CASE WHEN order_scope='question' THEN question_id ELSE '' END
                  ORDER BY source_sequence,event_id) previous FROM events
            ) SELECT count(*) FROM ordered WHERE timestamp<previous
        """).fetchone()[0]
        missing_sessions = connection.execute(
            "SELECT count(*) FROM events WHERE duration_scope='bundle' AND (session_id IS NULL OR bundle_id IS NULL)"
        ).fetchone()[0]
        ambiguous_sequence = connection.execute("""
            SELECT coalesce(sum(n-1),0) FROM (
              SELECT count(*) n FROM events GROUP BY source_namespace,learner_id,
                CASE WHEN order_scope='question' THEN question_id ELSE '' END,source_sequence HAVING count(*)>1)
        """).fetchone()[0]
        unsupported_bundles = connection.execute("""
            SELECT count(*) FROM (
              SELECT source_namespace,learner_id,session_id,count(DISTINCT bundle_id) bundles
              FROM events WHERE session_id IS NOT NULL GROUP BY source_namespace,learner_id,session_id
              HAVING count(DISTINCT bundle_id)>1)
        """).fetchone()[0]
    return {
        "dataset_id": dataset_id,
        "row_count": row_count,
        "manifest_row_count": manifest["row_count"],
        "unique_identities": distinct,
        "valid": row_count == distinct == manifest["row_count"] and not partition_errors,
        "checksums_verified": verify_checksums,
        "invalid_partitions": partition_errors,
        "known_timestamps": known,
        "unknown_timestamps": unknown,
        "shifted_timestamps": shifted,
        "timestamp_ties": int(time_ties),
        "source_order_timestamp_inversions": inversions,
        "ambiguous_source_sequences": int(ambiguous_sequence),
        "bundle_duration_without_identity": missing_sessions,
        "sessions_with_multiple_bundles": unsupported_bundles,
        "ordering_policy": "Timestamp ties and sessions are indivisible evaluation units; source sequence breaks display ties only.",
        "warnings": [
            message
            for condition, message in [
                (unknown > 0, "Missing timestamps prevent real-time trends."),
                (shifted > 0, "Shifted timestamps do not identify real calendar activity."),
                (
                    inversions > 0,
                    "Source order contains timestamp inversions; chronological views sort within known domains.",
                ),
                (
                    ambiguous_sequence > 0,
                    "Some source sequences are tied; event ID gives a deterministic display order, not proven chronology.",
                ),
                (
                    missing_sessions > 0,
                    "Bundle duration without stable session/bundle identity is excluded from elapsed-time totals.",
                ),
                (
                    unsupported_bundles > 0,
                    "Sessions contain several bundles; splits keep the whole session together.",
                ),
            ]
            if condition
        ],
    }
