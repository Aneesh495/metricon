from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from metricon.simulation.engine import SimulationConfig, simulate
from metricon.storage.hashing import atomic_json, file_hash

REGIMES = ("nominal", "slow_learning", "forgetting", "misspecified")


def simulation_campaign(destination: Path, seed: int = 2026, seeds: int = 30) -> dict[str, Any]:
    if seeds < 30:
        raise ValueError("Policy comparison requires at least thirty independent seeds per regime")
    destination.mkdir(parents=True, exist_ok=True)
    experiments = []
    raw_events = []
    raw_outcomes = []
    base = SimulationConfig(seed=seed, repetitions=seeds, retain_all_trajectories=True)
    for regime in REGIMES:
        for mode in ["questions", "time"]:
            config = replace(base, regime=regime, budget_mode=mode)
            result = simulate(config)
            for trajectory in result["trajectories"]:
                for event in trajectory["events"]:
                    raw_events.append(
                        {
                            "seed": trajectory["seed"],
                            "policy": trajectory["policy"],
                            "regime": regime,
                            "budget_mode": mode,
                            **event,
                        }
                    )
            for outcome in result["outcomes"]:
                raw_outcomes.append({**outcome, "budget_mode": mode})
            for policy in config.policies:
                outcomes = [row for row in result["outcomes"] if row["policy"] == policy]
                if len(outcomes) != seeds or any(
                    row["elapsed_seconds"] > config.budget_seconds for row in outcomes
                ):
                    raise AssertionError("Simulation budgets or seed coverage disagree")
                if mode == "questions" and any(
                    row["actions"] != config.question_budget for row in outcomes
                ):
                    raise AssertionError("Equal question budget was not respected")
            result.pop("trajectories")
            atomic_json(destination / f"{regime}-{mode}.json", result)
            experiments.append(
                {
                    "regime": regime,
                    "budget_mode": mode,
                    "summaries": result["summaries"],
                    "paired_comparisons": result["paired_comparisons"],
                    "hash": result["simulation_hash"],
                }
            )
    pq.write_table(
        pa.Table.from_pylist(raw_events), destination / "trajectories.parquet", compression="zstd"
    )
    pq.write_table(
        pa.Table.from_pylist(raw_outcomes), destination / "outcomes.parquet", compression="zstd"
    )
    summary = {
        "version": "policy-campaign/1",
        "synthetic": True,
        "seed": seed,
        "seeds_per_policy_regime": seeds,
        "regimes": REGIMES,
        "experiments": experiments,
        "trajectories": len(raw_events),
        "outcomes": len(raw_outcomes),
        "files": {
            path.name: file_hash(path) for path in sorted(destination.iterdir()) if path.is_file()
        },
        "interpretation": "The misspecified process differs from the policy's assumed transition and response parameters. All benefits are conditional simulator outcomes, not effects on real students.",
    }
    differences = [
        experiment["paired_comparisons"]["budget"]["mean_difference"] for experiment in experiments
    ]
    summary["adaptive_range_across_regimes"] = [
        float(np.min(differences)),
        float(np.max(differences)),
    ]
    atomic_json(destination / "campaign.json", summary)
    return summary
