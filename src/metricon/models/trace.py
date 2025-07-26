from __future__ import annotations

from typing import Any

import polars as pl

from metricon.features.history import domain, units
from metricon.models.base import load_model
from metricon.models.bkt import BKT, BKTParameters, step
from metricon.storage.catalog import Catalog
from metricon.storage.query import scan_events


def replay_bkt(
    catalog: Catalog,
    artifact_id: str,
    model_name: str,
    learner_id: str,
    offset: int = 0,
    limit: int = 100,
    fold: int = 0,
    maximum_history_rows: int = 100_000,
) -> dict[str, Any]:
    if not 1 <= limit <= 500 or offset < 0 or not 0 <= fold <= 9:
        raise ValueError("Invalid replay pagination")
    artifact = catalog.artifact(artifact_id)
    filename = f"fold-{fold}/{model_name}.model.json"
    if filename not in artifact["manifest"]["files"]:
        raise ValueError("Model is not in the committed experiment")
    model = load_model(catalog.root / "artifacts" / artifact_id / filename)
    if not isinstance(model, BKT):
        raise ValueError("Knowledge-state replay requires a BKT model")
    dataset_id = artifact["dataset_id"]
    selected = scan_events(catalog, dataset_id).filter(pl.col("learner_id") == learner_id)
    n = selected.select(pl.len()).collect().item()
    if n > maximum_history_rows:
        raise ValueError(
            "Replay history exceeds its explicit memory bound; select a smaller complete history"
        )
    rows = selected.collect().to_dicts()
    model.states.clear()
    trace = []
    position = 0
    domain_count = set()
    final_states: dict[str, Any] = {}
    for unit_index, unit in enumerate(units(rows)):
        before = {row["identity"]: model.explain(row) for row in unit}
        pending = []
        for row in unit:
            domain_count.add(domain(row))
            row_trace = {
                "event_id": row["event_id"],
                "identity": row["identity"],
                "question_id": row["question_id"],
                "source_sequence": row["source_sequence"],
                "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
                "time_semantics": row["time_semantics"],
                "order_scope": row["order_scope"],
                "unit": unit_index,
                "unit_size": len(unit),
                "correct": row["correct"],
                "prediction_before_unit": before[row["identity"]]["prediction"],
                "skills_before_unit": before[row["identity"]]["skills"],
                "skill_updates": [],
            }
            for skill in model.selected_skills(row):
                parameters = model.parameters_by_skill.get(skill, BKTParameters())
                key = model.state_key(row, skill)
                prior = model.states.get(key, parameters.initial)
                prediction, posterior, following = step(prior, row["correct"], parameters)
                update = {
                    "skill": skill,
                    "conditioning_prior": prior,
                    "conditional_prediction": prediction,
                    "answer_posterior": posterior,
                    "after_learning_transition": following,
                    "note": "Conditional updates within a completed unit are not pre-answer predictions.",
                }
                row_trace["skill_updates"].append(update)
                model.states[key] = following
                final_states[str(key)] = {
                    "skill": skill,
                    "state": following,
                    "fitted": model.diagnostics.get(skill, {}).get("fitted", False),
                }
            pending.append(row_trace)
        for row_trace in pending:
            if offset <= position < offset + limit:
                trace.append(row_trace)
            position += 1
    return {
        "artifact_id": artifact_id,
        "dataset_id": dataset_id,
        "model": model_name,
        "learner_id": learner_id,
        "rows": trace,
        "total": n,
        "offset": offset,
        "limit": limit,
        "final_states": final_states,
        "known_order_domains": len(domain_count),
        "policy": model.multi_skill,
        "parameter_fit_partition": "training only",
        "interpretation": "Retrospective replay from initial state using fitted parameters. Not the untouched held-out evaluation predictions.",
        "bundle_policy": "Predict every answer before observing any outcome in its unit; condition after the whole unit is observed.",
    }
