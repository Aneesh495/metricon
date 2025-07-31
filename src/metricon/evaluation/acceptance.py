from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from metricon.evaluation.benchmark import benchmark
from metricon.evaluation.campaigns import (
    generated_analytics,
    generated_ingestion,
    interruption_campaign,
)
from metricon.evaluation.evidence import (
    evidence_manifest,
    private_census,
    record_command,
    source_manifest,
    verify_files,
)
from metricon.evaluation.frozen import evaluate_frozen
from metricon.evaluation.plots import scientific_plots
from metricon.evaluation.research import public_research, synthetic_research
from metricon.schema.events import digest
from metricon.simulation.campaign import simulation_campaign
from metricon.storage.artifacts import verify_artifact
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def acceptance(root: Path) -> dict[str, Any]:
    repository = Path(__file__).parents[3]
    root = root.resolve()
    destination = root / "verification"
    destination.mkdir(parents=True, exist_ok=True)
    source = source_manifest(repository)
    atomic_json(destination / "source-manifest.json", source)
    commands = {}
    for name, command in [
        ("lint", [sys.executable, "-m", "ruff", "check", "src", "tests"]),
        ("python-tests", [sys.executable, "-m", "pytest", "-q"]),
        ("typescript", ["npm", "run", "check"]),
        ("web-tests", ["npm", "run", "test:web"]),
        ("production-build", ["npm", "run", "build"]),
        ("browser", ["npm", "run", "test:e2e"]),
    ]:
        commands[name] = record_command(repository, destination / "commands", name, command)
    census = private_census(repository, destination / "private-census.json")
    for path, execute in [
        (
            destination / "ingestion/ingestion.json",
            lambda: generated_ingestion(destination / "ingestion"),
        ),
        (
            destination / "analytics/analytics.json",
            lambda: generated_analytics(destination / "analytics"),
        ),
        (
            destination / "recovery/recovery.json",
            lambda: interruption_campaign(destination / "recovery"),
        ),
        (
            destination / "simulation/campaign.json",
            lambda: simulation_campaign(destination / "simulation"),
        ),
    ]:
        if not path.exists():
            execute()
    measured = benchmark(root / "benchmark")
    catalog = Catalog(root)
    synthetic = synthetic_research(catalog, destination / "synthetic")
    public = public_research(catalog, destination / "research")
    plot_id = scientific_plots(catalog, public["artifact_id"], root / "benchmark/benchmark.json")
    atomic_json(destination / "plots.json", {"artifact_id": plot_id, "run": public["artifact_id"]})
    gates = assess(root, census)
    paths = [
        destination / "source-manifest.json",
        destination / "private-census.json",
        destination / "ingestion/ingestion.json",
        destination / "analytics/analytics.json",
        destination / "recovery/recovery.json",
        destination / "simulation/campaign.json",
        destination / "synthetic/synthetic.json",
        destination / "research/public.json",
        destination / "plots.json",
        root / "benchmark/benchmark.json",
        destination / "browser/e2e.json",
    ]
    paths += sorted((destination / "commands").glob("*.json")) + sorted(
        (destination / "commands").glob("*.log")
    )
    paths += sorted((root / "benchmark").glob("repetition-*.json"))
    paths += sorted((destination / "simulation").glob("*.parquet"))
    paths += sorted((destination / "synthetic").glob("seed-*.json"))
    payload = {
        "version": "acceptance/1",
        "system_correctness": all(gates.values()),
        "gates": gates,
        "model_quality_targets_met": synthetic["model_quality_targets_met"],
        "performance_targets_met": all(
            row["median_rows_per_second"] >= 50000
            and all(query["p95_seconds"] < 0.5 for query in row["queries"].values())
            for row in measured["summaries"].values()
        ),
        "source_hash": source["hash"],
        "commands": commands,
        "evidence": evidence_manifest(paths, root),
        "runs": [
            public["artifact_id"],
            *[row["artifact_id"] for row in synthetic["datasets"]],
            plot_id,
        ],
    }
    if source_manifest(repository)["hash"] != source["hash"]:
        raise RuntimeError(
            "Source changed during acceptance; retain raw evidence and rerun the final checks"
        )
    atomic_json(destination / "ACCEPTANCE.json", payload)
    if not payload["system_correctness"]:
        raise RuntimeError("Acceptance has incomplete or failed correctness gates")
    return {
        "path": str(destination / "ACCEPTANCE.json"),
        "system_correctness": True,
        "model_quality_targets_met": payload["model_quality_targets_met"],
        "performance_targets_met": payload["performance_targets_met"],
    }


def assess(root: Path, census: dict[str, Any]) -> dict[str, bool]:
    destination = root / "verification"
    ingestion = read(destination / "ingestion/ingestion.json")
    analytics = read(destination / "analytics/analytics.json")
    recovery = read(destination / "recovery/recovery.json")
    simulation = read(destination / "simulation/campaign.json")
    synthetic = read(destination / "synthetic/synthetic.json")
    public = read(destination / "research/public.json")
    measured = read(root / "benchmark/benchmark.json")
    browser = read(destination / "browser/e2e.json")
    catalog = Catalog(root)
    experiments = [public["artifact_id"], *[row["artifact_id"] for row in synthetic["datasets"]]]
    for identifier in experiments:
        evaluate_frozen(catalog, identifier)
        manifest = catalog.artifact(identifier)["manifest"]
        if "fold-0/preprocessing.json" not in manifest["files"]:
            raise ValueError("Research run lacks preprocessing fitting scopes")
    return {
        "install_build": all(
            read(path)["exit_code"] == 0 for path in (destination / "commands").glob("*.json")
        ),
        "ingestion": ingestion["cases"] >= 10000
        and ingestion["counts"] == ingestion["reference_counts"]
        and ingestion["retry_idempotent"],
        "scale": set(map(int, measured["summaries"])) == {100000, 1000000, 10000000}
        and all(
            sum(record["rows"] == size for record in measured["repetitions"]) >= 5
            for size in [100000, 1000000, 10000000]
        )
        and all(
            record["peak_import_rss_bytes"] < 2 * 1024**3 for record in measured["repetitions"]
        ),
        "crash_safety": recovery["cases"] >= 100
        and all(record["exit_code"] == 91 for record in recovery["results"]),
        "analytics": analytics["datasets"] >= 1000,
        "models_evaluation": synthetic["system_correctness"] and public["frozen_verification"],
        "real_data": public["rows"] >= 200000 and public["learners"] >= 1000,
        "simulation": simulation["seeds_per_policy_regime"] >= 30
        and len(simulation["regimes"]) >= 4,
        "product": browser["passed"] and len(browser["workflows"]) >= 8,
        "size": census["minimum_met"],
    }


def verify_evidence(root: Path) -> dict[str, Any]:
    root = root.resolve()
    destination = root / "verification"
    path = destination / "ACCEPTANCE.json"
    if not path.is_file():
        raise ValueError("ACCEPTANCE.json is missing; verification does not regenerate evidence")
    result = read(path)
    errors = verify_files(root, result["evidence"])
    current = source_manifest(Path(__file__).parents[3])
    if current["hash"] != result["source_hash"]:
        errors.append("Actual source/test/lock contents differ from the accepted source snapshot")
    catalog = Catalog(root)
    for identifier in result["runs"]:
        if not verify_artifact(catalog, identifier)["valid"]:
            errors.append(f"Run artifact changed: {identifier}")
    gates = assess(root, read(destination / "private-census.json"))
    if gates != result["gates"] or not all(gates.values()):
        errors.append("Required gates are incomplete or disagree with immutable evidence")
    if digest(read(destination / "source-manifest.json")["files"]) != result["source_hash"]:
        errors.append("Source snapshot manifest was altered")
    if errors:
        raise ValueError("Evidence verification failed: " + "; ".join(errors))
    return {"valid": True, "path": str(path), "gates": gates, "regenerated": False}
