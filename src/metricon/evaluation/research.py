from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metricon.evaluation.experiment import ExperimentConfig, run_experiment
from metricon.evaluation.frozen import evaluate_frozen
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.demo import demo_workspace
from metricon.ingest.ednet import create_subset, download_ednet
from metricon.ingest.pipeline import import_file
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json
from metricon.storage.query import analytical_connection
from metricon.storage.lineage import source_code_hash

FIXED_SYNTHETIC_SEEDS = (17, 41, 73, 101, 137)


def public_dataset(catalog: Catalog) -> dict[str, Any]:
    state_path = catalog.root / "research-state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        dataset = catalog.dataset(state["dataset_id"])
        with analytical_connection(catalog, state["dataset_id"]) as connection:
            learners = connection.execute(
                "SELECT count(DISTINCT learner_id) FROM events"
            ).fetchone()[0]
        if dataset["row_count"] >= 200000 and learners >= 1000:
            return state
    cache = catalog.root / "cache"
    for kind in ["kt1", "contents"]:
        download_ednet(cache, kind)
    subset = cache / "subset.ndjson"
    manifest = create_subset(
        cache / "EdNet-KT1.zip", cache / "contents.zip", subset, 200000, 1000, 2026
    )
    workspace = catalog.create_workspace("EdNet KT1 deterministic complete sequences", "research")
    result = import_file(catalog, workspace["id"], subset, AdapterOptions("ndjson", "ednet-kt1"))
    state = {
        "workspace": workspace["id"],
        "dataset_id": result["dataset_id"],
        "subset_manifest": manifest,
    }
    atomic_json(state_path, state)
    return state


def public_research(catalog: Catalog, destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    state = public_dataset(catalog)
    for kind in ["kt1", "contents"]:
        download_ednet(catalog.root / "cache", kind)
    configuration = ExperimentConfig(seed=2026)
    artifact = run_experiment(
        catalog,
        state["dataset_id"],
        configuration,
        progress=lambda _, message: print(message, flush=True),
    )
    frozen = evaluate_frozen(catalog, artifact)
    with analytical_connection(catalog, state["dataset_id"]) as connection:
        learners = connection.execute("SELECT count(DISTINCT learner_id) FROM events").fetchone()[0]
    report = {
        "dataset_id": state["dataset_id"],
        "artifact_id": artifact,
        "rows": catalog.dataset(state["dataset_id"])["row_count"],
        "learners": learners,
        "frozen_verification": frozen["valid"],
        "raw_report": str(catalog.root / "artifacts" / artifact / "report.json"),
        "provenance": {
            kind: json.loads((catalog.root / "cache" / name).read_text())
            for kind, name in [
                ("kt1", "EdNet-KT1.provenance.json"),
                ("contents", "contents.provenance.json"),
            ]
        },
    }
    state["artifact_id"] = artifact
    atomic_json(catalog.root / "research-state.json", state)
    atomic_json(destination / "public.json", report)
    return report


def synthetic_research(catalog: Catalog, destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    evidence = []
    pipeline_hash = source_code_hash(Path(__file__).parents[1])["hash"]
    for seed in FIXED_SYNTHETIC_SEEDS:
        path = destination / f"seed-{seed}.json"
        if path.exists():
            previous = json.loads(path.read_text())
            run_report = json.loads(
                (catalog.root / "artifacts" / previous["artifact_id"] / "report.json").read_text()
            )
            artifact = catalog.artifact(previous["artifact_id"])
            if run_report.get("source_code", {}).get("hash") == pipeline_hash and (
                artifact["manifest"]["files"].get("dependency.lock")
                == run_report["environment"]["lock_sha256"]
            ):
                evidence.append(previous)
                continue
            archive = destination / "previous"
            archive.mkdir(exist_ok=True)
            path.rename(archive / f"seed-{seed}-{previous['artifact_id']}.json")
        demo = demo_workspace(catalog, seed, learners=300, attempts=90)
        dataset = demo["workspace"]["dataset_id"]
        artifact = run_experiment(
            catalog,
            dataset,
            ExperimentConfig(seed=seed),
            progress=lambda _, message: print(f"Synthetic seed {seed}: {message}", flush=True),
        )
        report = json.loads((catalog.root / "artifacts" / artifact / "report.json").read_text())
        models = report["folds"][0]["models"]
        baseline = models["global"]["test"]["log_loss"]
        bkt = models["bkt"]["test"]["log_loss"]
        result = {
            "seed": seed,
            "dataset_id": dataset,
            "artifact_id": artifact,
            "rows": 27000,
            "learners": 300,
            "test_n": models["global"]["test"]["n"],
            "global_log_loss": baseline,
            "bkt_log_loss": bkt,
            "relative_improvement": (baseline - bkt) / baseline,
            "model_quality_target_met": bkt <= baseline * 0.95,
            "frozen_valid": evaluate_frozen(catalog, artifact)["valid"],
            "generator": {
                "skills": 3,
                "initial": 0.2,
                "learning": 0.1,
                "slip": 0.1,
                "guess": 0.2,
                "forgetting": 0,
                "full_sequences": True,
                "latent_states_exported": False,
            },
        }
        atomic_json(path, result)
        evidence.append(result)
    result = {
        "datasets": evidence,
        "fixed_seeds": FIXED_SYNTHETIC_SEEDS,
        "model_quality_targets_met": all(row["model_quality_target_met"] for row in evidence),
        "system_correctness": all(row["frozen_valid"] for row in evidence),
        "interpretation": "Identifiable known-process synthetic workloads; success here does not establish validity on real learners",
    }
    atomic_json(destination / "synthetic.json", result)
    return result
