from __future__ import annotations

import json
from typing import Any

from metricon.analytics.statistics import midrank_percentile, wilson
from metricon.schema.events import digest
from metricon.storage.artifacts import ArtifactWriter
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json, read_json
from metricon.storage.query import analytical_connection

METRIC_DEFINITIONS = {
    "all_attempt_accuracy": "Correct accepted attempts divided by all accepted attempts.",
    "first_attempt_accuracy": "Correct first attempts within learner/question/order domain divided by eligible first attempts.",
    "streak": "Consecutive correct answers within a known order domain; unknown global order is never inferred.",
    "retries_before_success": "Incorrect answers before the first correct answer within learner/question; unsolved items are censored.",
    "duration": "Known event durations plus one observed bundle duration per learner/session/bundle; no unknown imputation.",
    "skill_accuracy": "An event contributes once to each explicit skill tag; denominators across skills overlap.",
    "elapsed_time_trend": "Only real timestamps; shifted time appears as relative order and never calendar trends.",
}


def _rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _intervals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row["accuracy"] = wilson(int(row.pop("successes")), int(row.pop("n")))
    return rows


class Analytics:
    def __init__(self, catalog: Catalog, dataset_id: str):
        self.catalog = catalog
        self.dataset_id = dataset_id

    def overview(self, learner_id: str | None = None) -> dict[str, Any]:
        filters = "WHERE learner_id=?" if learner_id else ""
        params = [learner_id] if learner_id else []
        with analytical_connection(self.catalog, self.dataset_id) as connection:
            connection.execute(
                f"CREATE TEMP TABLE selected AS SELECT * FROM events {filters}", params
            )
            summary = _rows(
                connection.execute("""
                SELECT count(*) n, coalesce(sum(correct::INTEGER),0) successes,
                count(DISTINCT learner_id) learners, count(DISTINCT question_id) questions,
                count(timestamp) timestamped, count(duration_ms) duration_known,
                count(*) FILTER (WHERE order_scope='question') question_only,
                count(*) FILTER (WHERE time_semantics='shifted') shifted
                FROM selected
            """)
            )[0]
            first = _rows(
                connection.execute("""
                WITH ranked AS (
                  SELECT *, row_number() OVER(PARTITION BY source_namespace,learner_id,question_id
                    ORDER BY timestamp NULLS LAST,source_sequence,event_id) rn FROM selected
                ) SELECT count(*) n,coalesce(sum(correct::INTEGER),0) successes FROM ranked WHERE rn=1
            """)
            )[0]
            duration = _rows(
                connection.execute("""
                WITH eligible AS (
                  SELECT *,row_number() OVER(PARTITION BY source_namespace,learner_id,session_id,bundle_id
                    ORDER BY source_sequence,event_id) rn FROM selected WHERE duration_ms IS NOT NULL
                ) SELECT count(*) n,median(duration_ms) median_ms,
                  quantile_cont(duration_ms,.25) q25_ms,quantile_cont(duration_ms,.75) q75_ms,
                  quantile_cont(duration_ms,.9) p90_ms,sum(duration_ms) total_ms
                  FROM eligible WHERE duration_scope='event' OR
                    (duration_scope='bundle' AND rn=1 AND session_id IS NOT NULL AND bundle_id IS NOT NULL)
            """)
            )[0]
            retries = _rows(
                connection.execute("""
                WITH ranked AS (
                  SELECT *,row_number() OVER(PARTITION BY source_namespace,learner_id,question_id
                    ORDER BY timestamp NULLS LAST,source_sequence,event_id)-1 attempt_position FROM selected
                ), groups AS (
                  SELECT source_namespace,learner_id,question_id,min(attempt_position) FILTER(WHERE correct) retries,
                    count(*) attempts FROM ranked GROUP BY source_namespace,learner_id,question_id
                ) SELECT count(*) questions,count(retries) solved,count(*) FILTER(WHERE retries IS NULL) censored,
                   avg(retries) mean_retries_before_success,median(retries) median_retries_before_success FROM groups
            """)
            )[0]
        accuracy = wilson(int(summary.pop("successes")), int(summary.pop("n")))
        return {
            "dataset_id": self.dataset_id,
            "learner_id": learner_id,
            "accuracy": accuracy,
            "first_attempt_accuracy": wilson(int(first["successes"]), int(first["n"])),
            "coverage": summary,
            "durations": duration,
            "retries": retries,
            "definitions": METRIC_DEFINITIONS,
            "small_sample": accuracy["n"] < 30,
            "mastery_interpretation": "Last correctness and observed accuracy do not certify mastery.",
        }

    def groups(
        self,
        dimension: str = "question",
        offset: int = 0,
        limit: int = 50,
        learner_id: str | None = None,
        search: str = "",
    ) -> dict[str, Any]:
        if dimension not in {"question", "skill", "learner"}:
            raise ValueError("Unknown group dimension")
        if offset < 0 or not 1 <= limit <= 500:
            raise ValueError("Invalid pagination")
        column = {"question": "question_id", "skill": "skill", "learner": "learner_id"}[dimension]
        source = (
            "(SELECT *,unnest(skills) AS skill FROM events)" if dimension == "skill" else "events"
        )
        filters = [f"{column} LIKE ?"]
        params: list[Any] = [f"%{search}%"]
        if learner_id:
            filters.append("learner_id=?")
            params.append(learner_id)
        where = " AND ".join(filters)
        with analytical_connection(self.catalog, self.dataset_id) as connection:
            total = connection.execute(
                f"SELECT count(DISTINCT {column}) FROM {source} WHERE {where}", params
            ).fetchone()[0]
            rows = _rows(
                connection.execute(
                    f"""
                SELECT {column} AS id,count(*) n,sum(correct::INTEGER) successes,
                count(DISTINCT learner_id) learners,count(DISTINCT question_id) questions,
                count(duration_ms) known_durations,min(timestamp) first_timestamp,max(timestamp) last_timestamp
                FROM {source} WHERE {where} GROUP BY {column} ORDER BY n DESC,id LIMIT ? OFFSET ?
            """,
                    [*params, limit, offset],
                )
            )
        for row in rows:
            for name in ["first_timestamp", "last_timestamp"]:
                row[name] = row[name].isoformat() if row[name] else None
        return {
            "rows": _intervals(rows),
            "total": total,
            "offset": offset,
            "limit": limit,
            "dimension": dimension,
            "overlapping_denominators": dimension == "skill",
        }

    def history(
        self, learner_id: str, question_id: str | None = None, limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        if not 1 <= limit <= 500 or offset < 0:
            raise ValueError("Invalid pagination")
        where = "learner_id=?"
        params: list[Any] = [learner_id]
        if question_id:
            where += " AND question_id=?"
            params.append(question_id)
        with analytical_connection(self.catalog, self.dataset_id) as connection:
            total = connection.execute(
                f"SELECT count(*) FROM events WHERE {where}", params
            ).fetchone()[0]
            rows = _rows(
                connection.execute(
                    f"""
                SELECT event_id,source_namespace,question_id,skills,correct,attempt_kind,source_sequence,
                timestamp,duration_ms,session_id,bundle_id,order_scope,time_semantics,provenance
                FROM events WHERE {where}
                ORDER BY source_namespace,CASE WHEN order_scope='question' THEN question_id ELSE '' END,
                  timestamp NULLS LAST,source_sequence,event_id LIMIT ? OFFSET ?
            """,
                    [*params, limit, offset],
                )
            )
        for row in rows:
            row["timestamp"] = row["timestamp"].isoformat() if row["timestamp"] else None
            row["provenance"] = json.loads(row["provenance"])
        return {
            "rows": rows,
            "total": total,
            "offset": offset,
            "limit": limit,
            "ordering": "Source/known order domain, then timestamp/sequence/ID. Domains are not one global chronology.",
        }

    def streaks(self, learner_id: str) -> dict[str, Any]:
        with analytical_connection(self.catalog, self.dataset_id) as connection:
            rows = _rows(
                connection.execute(
                    """
              WITH ordered AS (
                SELECT *,CASE WHEN order_scope='question' THEN question_id ELSE '' END domain,
                  sum(CASE WHEN correct THEN 0 ELSE 1 END) OVER (
                    PARTITION BY source_namespace,learner_id,CASE WHEN order_scope='question' THEN question_id ELSE '' END
                    ORDER BY timestamp NULLS LAST,source_sequence,event_id ROWS UNBOUNDED PRECEDING) failures
                FROM events WHERE learner_id=?
              ), runs AS (
                SELECT source_namespace,domain,failures,count(*) length FROM ordered WHERE correct
                GROUP BY source_namespace,domain,failures
              ) SELECT source_namespace,domain,max(length) longest_correct_streak FROM runs
                GROUP BY source_namespace,domain ORDER BY source_namespace,domain
            """,
                    [learner_id],
                )
            )
        return {
            "domains": rows,
            "global_streak_available": bool(rows) and all(row["domain"] == "" for row in rows),
            "definition": METRIC_DEFINITIONS["streak"],
        }

    def trend(
        self, learner_id: str, bins: int = 80, axis: str = "order", question_id: str | None = None
    ) -> dict[str, Any]:
        if not 2 <= bins <= 500 or axis not in {"order", "time"}:
            raise ValueError("Invalid trend parameters")
        where = "learner_id=?"
        params: list[Any] = [learner_id]
        if question_id:
            where += " AND question_id=?"
            params.append(question_id)
        with analytical_connection(self.catalog, self.dataset_id) as connection:
            domains = connection.execute(
                f"SELECT count(DISTINCT source_namespace || ':' || CASE WHEN order_scope='question' THEN question_id ELSE '' END) FROM events WHERE {where}",
                params,
            ).fetchone()[0]
            if axis == "order" and domains > 1:
                return {
                    "available": False,
                    "reason": "Choose a question or one known order domain; global chronology is unknown.",
                    "series": [],
                }
            if axis == "time":
                where += " AND timestamp IS NOT NULL AND time_semantics='real'"
                axis_value = "epoch(timestamp)"
                grouping = f"ntile({bins}) OVER(ORDER BY timestamp,source_sequence,event_id)"
            else:
                axis_value = "source_sequence"
                grouping = (
                    f"ntile({bins}) OVER(ORDER BY timestamp NULLS LAST,source_sequence,event_id)"
                )
            rows = _rows(
                connection.execute(
                    f"""
                WITH ordered AS (SELECT *,{axis_value} x,{grouping} bucket FROM events WHERE {where})
                SELECT bucket,min(x) x_start,max(x) x_end,count(*) n,sum(correct::INTEGER) successes,
                min(correct::INTEGER) minimum,max(correct::INTEGER) maximum FROM ordered
                GROUP BY bucket ORDER BY bucket
            """,
                    params,
                )
            )
        return {
            "available": bool(rows),
            "axis": "elapsed UTC seconds" if axis == "time" else "source event order",
            "series": _intervals(rows),
            "retains_extrema": True,
            "eligible": "real timestamps only" if axis == "time" else "one known order domain",
        }

    def cohort(self, learner_id: str, minimum_attempts: int = 20) -> dict[str, Any]:
        with analytical_connection(self.catalog, self.dataset_id) as connection:
            target_items = connection.execute(
                "SELECT count(DISTINCT question_id) FROM events WHERE learner_id=?", [learner_id]
            ).fetchone()[0]
            rows = _rows(
                connection.execute(
                    """WITH target_items AS (SELECT DISTINCT source_namespace,question_id FROM events WHERE learner_id=?)
                SELECT learner_id,count(*) n,avg(correct::INTEGER) accuracy,count(DISTINCT question_id) shared_items
                FROM events JOIN target_items USING(source_namespace,question_id)
                GROUP BY learner_id HAVING count(*)>=? ORDER BY learner_id""",
                    [learner_id, minimum_attempts],
                )
            )
        target = next((row for row in rows if row["learner_id"] == learner_id), None)
        peers = [
            row
            for row in rows
            if row["learner_id"] != learner_id and row["shared_items"] >= max(2, target_items * 0.5)
        ]
        if not peers or target is None:
            return {
                "available": False,
                "reason": "No comparable observed peers with enough attempts and shared items",
                "filter": "At least two shared items, half the target item set, and the minimum attempt denominator",
            }
        import numpy as np

        workspace = self.catalog.workspace(self.catalog.dataset(self.dataset_id)["workspace_id"])
        return {
            "available": True,
            "percentile": midrank_percentile(
                target["accuracy"], np.asarray([row["accuracy"] for row in peers])
            ),
            "cohort_id": self.dataset_id,
            "eligible_peers": len(peers),
            "minimum_attempts": minimum_attempts,
            "target_attempts": target["n"],
            "shared_item_fraction_minimum": 0.5,
            "target_items": target_items,
            "tie_method": "midrank",
            "synthetic": workspace["kind"] == "synthetic",
            "comparison_limit": "Matched observed item support; exposure frequencies and selection may still differ. Descriptive, not a population ability ranking.",
        }

    def materialize(self, parameters: dict[str, Any]) -> str:
        key = digest([self.dataset_id, "analytics/1", parameters])
        for artifact in self.catalog.artifacts(self.dataset_id, "analytics"):
            metadata = self.catalog.artifact(artifact["id"])["manifest"]["metadata"]
            if metadata.get("query_hash") == key:
                return artifact["id"]
        result = self.overview(parameters.get("learner_id"))
        with ArtifactWriter(self.catalog, "analytics", self.dataset_id) as writer:
            atomic_json(writer.path / "overview.json", result)
            return writer.publish(
                {"query_hash": key, "parameters": parameters, "version": "analytics/1"}
            )

    def cached_overview(self, parameters: dict[str, Any]) -> dict[str, Any]:
        identifier = self.materialize(parameters)
        result = read_json(self.catalog.root / "artifacts" / identifier / "overview.json")
        result["artifact_id"] = identifier
        return result
