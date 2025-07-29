from __future__ import annotations

from typing import Any

from metricon.analytics.statistics import wilson
from metricon.storage.catalog import Catalog
from metricon.storage.query import analytical_connection


def sessions(
    catalog: Catalog,
    dataset_id: str,
    learner_id: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    if offset < 0 or not 1 <= limit <= 500:
        raise ValueError("Session pagination is outside bounds")
    condition = "WHERE session_id IS NOT NULL" + (" AND learner_id=?" if learner_id else "")
    parameters = [learner_id] if learner_id else []
    with analytical_connection(catalog, dataset_id) as connection:
        total = connection.execute(
            f"SELECT count(*) FROM (SELECT DISTINCT source_namespace,learner_id,session_id FROM events {condition})",
            parameters,
        ).fetchone()[0]
        cursor = connection.execute(
            f"""WITH duration AS (
            SELECT source_namespace,learner_id,session_id,bundle_id,duration_scope,duration_ms,
                row_number() OVER(PARTITION BY source_namespace,learner_id,session_id,bundle_id ORDER BY source_sequence,event_id) bundle_rank
            FROM events {condition}
        ), times AS (
            SELECT source_namespace,learner_id,session_id,
                sum(duration_ms) FILTER(WHERE duration_scope='event' OR (duration_scope='bundle' AND bundle_id IS NOT NULL AND bundle_rank=1)) known_duration_ms,
                count(duration_ms) FILTER(WHERE duration_scope='event' OR (duration_scope='bundle' AND bundle_id IS NOT NULL AND bundle_rank=1)) duration_observations
            FROM duration GROUP BY source_namespace,learner_id,session_id
        ) SELECT e.source_namespace,e.learner_id,e.session_id,count(*) n,sum(correct::INTEGER) successes,
            count(DISTINCT question_id) questions,count(DISTINCT e.bundle_id) bundles,
            min(timestamp)::VARCHAR first_timestamp,max(timestamp)::VARCHAR last_timestamp,
            bool_or(time_semantics='shifted') shifted,t.known_duration_ms,t.duration_observations
            FROM events e JOIN times t USING(source_namespace,learner_id,session_id) {condition}
            GROUP BY e.source_namespace,e.learner_id,e.session_id,t.known_duration_ms,t.duration_observations
            ORDER BY e.source_namespace,e.learner_id,e.session_id LIMIT ? OFFSET ?""",
            [*parameters, *parameters, limit, offset],
        )
        columns = [value[0] for value in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    for row in rows:
        row["accuracy"] = wilson(int(row["successes"]), int(row["n"]))
    return {
        "dataset_id": dataset_id,
        "rows": rows,
        "total": total,
        "offset": offset,
        "limit": limit,
        "eligibility": "Explicit session identifiers only; known durations deduplicate repeated bundle elapsed time",
        "unknown_session_events": "Excluded from session counts; remain eligible for attempt metrics",
        "time_interpretation": "Shifted timestamps support source-relative sequence spans, never real calendar behavior",
    }
