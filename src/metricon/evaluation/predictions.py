from __future__ import annotations

from typing import Any

import duckdb

from metricon.evaluation.metrics import metric_summary
from metricon.storage.catalog import Catalog


class PredictionInspector:
    def __init__(self, catalog: Catalog, artifact_id: str, fold: int = 0):
        if not 0 <= fold <= 9:
            raise ValueError("Fold must be between zero and nine")
        artifact = catalog.artifact(artifact_id)
        filename = f"fold-{fold}/predictions.parquet"
        if filename not in artifact["manifest"]["files"]:
            raise ValueError("Raw predictions do not exist for this artifact/fold")
        self.catalog = catalog
        self.artifact_id = artifact_id
        self.path = catalog.root / "artifacts" / artifact_id / filename

    def rows(
        self,
        model: str,
        partition: str = "test",
        learner: str | None = None,
        question: str | None = None,
        offset: int = 0,
        limit: int = 50,
        sort: str = "identity",
    ) -> dict[str, Any]:
        if partition not in {"validation", "test"} or sort not in {
            "identity",
            "largest_error",
            "confidence",
        }:
            raise ValueError("Unsupported prediction filter or ordering")
        if offset < 0 or not 1 <= limit <= 500:
            raise ValueError("Prediction page limit must be 1..500")
        where = ["model=?", "partition=?"]
        arguments: list[Any] = [model, partition]
        if learner:
            where.append("learner_id=?")
            arguments.append(learner)
        if question:
            where.append("question_id=?")
            arguments.append(question)
        ordering = {
            "identity": "identity",
            "largest_error": "abs(correct::INTEGER-probability) DESC,identity",
            "confidence": "abs(probability-.5) DESC,identity",
        }[sort]
        with duckdb.connect(":memory:") as connection:
            connection.read_parquet(str(self.path)).create_view("predictions")
            predicate = " AND ".join(where)
            n = connection.execute(
                f"SELECT count(*) FROM predictions WHERE {predicate}", arguments
            ).fetchone()[0]
            cursor = connection.execute(
                f"""SELECT identity,learner_id,question_id,skills,correct,probability,
                calibrated_probability,abs(correct::INTEGER-probability) absolute_error
                FROM predictions WHERE {predicate} ORDER BY {ordering} LIMIT ? OFFSET ?""",
                [*arguments, limit, offset],
            )
            columns = [column[0] for column in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return {
            "artifact_id": self.artifact_id,
            "model": model,
            "partition": partition,
            "rows": rows,
            "total": n,
            "offset": offset,
            "limit": limit,
            "sort": sort,
            "interpretation": "Diagnostic inspection of saved predictions; no fitting or hyperparameter selection occurs here.",
        }

    def slice(
        self,
        model: str,
        learner: str | None = None,
        skill: str | None = None,
        calibrated: bool = False,
    ) -> dict[str, Any]:
        filters = ["model=?", "partition='test'"]
        arguments: list[Any] = [model]
        if learner:
            filters.append("learner_id=?")
            arguments.append(learner)
        if skill:
            filters.append("list_contains(skills,?)")
            arguments.append(skill)
        column = "calibrated_probability" if calibrated else "probability"
        with duckdb.connect(":memory:") as connection:
            connection.read_parquet(str(self.path)).create_view("predictions")
            selected = connection.execute(
                f"SELECT correct,{column} FROM predictions WHERE {' AND '.join(filters)}", arguments
            ).fetchnumpy()
        p = selected[column]
        if len(p) and getattr(p, "mask", None) is not None and p.mask.any():
            raise ValueError("Calibrated predictions were not saved for this run")
        return {
            "model": model,
            "learner": learner,
            "skill": skill,
            "calibrated": calibrated,
            "metrics": metric_summary(selected["correct"], p),
            "population": "Saved test partition restricted by selected learner and/or skill",
            "selection_limit": "Post-hoc slices are diagnostic; selecting the best slice does not establish generalization.",
        }
