from __future__ import annotations

import json
import sys
import time
import subprocess
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
from metricon.features.leakage import (
    FitScope,
    audit_feature_names,
    audit_dependencies,
    audit_fit_scope,
    prefix_invariance,
    audit_preprocessing_manifest,
)
from metricon.evaluation.splits import SplitManifest, audit_split
from metricon.storage.query import scan_events
from metricon.quality.audit import dataset_audit
from metricon.storage.hashing import file_hash
from metricon.storage.lineage import source_code_hash
from metricon.evaluation.workloads import workload_reference, reference_checksum

REQUIRED_COMMANDS = {
    "python-install",
    "node-install",
    "api-build",
    "lint",
    "python-tests",
    "typescript",
    "web-tests",
    "production-build",
    "browser",
}


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
        ("python-install", ["uv", "sync", "--locked"]),
        ("node-install", ["npm", "ci"]),
        ("lint", [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"]),
        ("python-tests", [sys.executable, "-m", "pytest", "-q"]),
        ("typescript", ["npm", "run", "check"]),
        ("web-tests", ["npm", "run", "test:web"]),
        ("production-build", ["npm", "run", "build"]),
        ("api-build", ["uv", "build", "--wheel", "--out-dir", str(root / "build")]),
        ("browser", ["npm", "run", "test:e2e"]),
    ]:
        commands[name] = record_command(repository, destination / "commands", name, command)
    census = private_census(repository, destination / "private-census.json")
    pipeline_hash = source_code_hash(repository / "src/metricon")["hash"]
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
        if not path.exists() or read(path).get("pipeline_hash") != pipeline_hash:
            if path.parent.exists():
                archive = destination / "previous"
                archive.mkdir(exist_ok=True)
                path.parent.rename(archive / f"{path.parent.name}-{time.time_ns()}")
            outcome = execute()
            outcome["pipeline_hash"] = pipeline_hash
            atomic_json(path, outcome)
    measured = benchmark(root / "benchmark")
    catalog = Catalog(root)
    synthetic = synthetic_research(catalog, destination / "synthetic")
    public = public_research(catalog, destination / "research")
    research_audit = audit_research(
        catalog, [public["artifact_id"], *[row["artifact_id"] for row in synthetic["datasets"]]]
    )
    atomic_json(destination / "research-audit.json", research_audit)
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
        destination / "research-audit.json",
        destination / "plots.json",
        root / "benchmark/benchmark.json",
        root / "benchmark/hardware.json",
        destination / "browser/e2e.json",
    ]
    paths += sorted((destination / "commands").glob("*.json")) + sorted(
        (destination / "commands").glob("*.log")
    )
    paths += sorted((root / "benchmark").glob("repetition-*.json"))
    paths += sorted((root / "benchmark").glob("worker-*.log"))
    paths += sorted((root / "benchmark/corpora").glob("*.manifest.json"))
    paths += sorted((root / "benchmark/fitting").glob("fit-*.json"))
    paths += sorted((root / "benchmark/fitting").glob("fit-*.log"))
    paths += sorted((destination / "analytics/inputs").glob("*.ndjson"))
    paths += [destination / "ingestion/cases.ndjson"]
    paths += sorted((destination / "recovery").glob("interruption-*.log"))
    paths += sorted((catalog.root / "cache").glob("*.provenance.json"))
    paths += [catalog.root / "cache/subset.manifest.json"]
    paths += sorted((destination / "simulation").glob("*.parquet"))
    paths += sorted((destination / "synthetic").glob("seed-*.json"))
    paths += sorted((destination / "simulation").glob("*-*.json"))
    paths += sorted((destination / "browser").glob("*.png"))
    paths += [destination / "browser/playwright.json"]
    paths += sorted((root / "benchmark/source-snapshots").rglob("*.*"))
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
    research_audit = read(destination / "research-audit.json")
    measured = read(root / "benchmark/benchmark.json")
    browser = read(destination / "browser/e2e.json")
    catalog = Catalog(root)
    experiments = [public["artifact_id"], *[row["artifact_id"] for row in synthetic["datasets"]]]
    reference_contents = {size: reference_checksum(size) for size in [100000, 1000000, 10000000]}
    for identifier in experiments:
        evaluate_frozen(catalog, identifier)
        manifest = catalog.artifact(identifier)["manifest"]
        if "fold-0/preprocessing.json" not in manifest["files"]:
            raise ValueError("Research run lacks preprocessing fitting scopes")
        report = read(catalog.root / "artifacts" / identifier / "report.json")
        if manifest["files"].get("dependency.lock") != report["environment"]["lock_sha256"]:
            raise ValueError("Research run lacks its exact dependency lock file")
    return {
        "install_build": all(
            (destination / "commands" / f"{name}.json").is_file()
            and read(destination / "commands" / f"{name}.json")["exit_code"] == 0
            for name in REQUIRED_COMMANDS
        ),
        "ingestion": ingestion["cases"] >= 10000
        and ingestion["counts"] == ingestion["reference_counts"]
        and ingestion["retry_idempotent"],
        "scale": set(map(int, measured["summaries"])) == {100000, 1000000, 10000000}
        and all(
            sum(record["rows"] == size for record in measured["repetitions"]) >= 5
            for size in [100000, 1000000, 10000000]
        )
        and all(record["peak_import_rss_bytes"] < 2 * 1024**3 for record in measured["repetitions"])
        and all(
            record["counts"]
            == {key: record["manifest"]["quality"][key] for key in record["counts"]}
            and record["counts"]["received"] == record["rows"]
            and record["counts"] == workload_reference(record["rows"])
            and record["independent_content"] == reference_contents[record["rows"]]
            and record["features"]["rows"] == record["counts"]["accepted"]
            and "native_thread_pools" in record
            and record["polars_threads"] == 2
            and all(pool["num_threads"] == 1 for pool in record["native_thread_pools"])
            for record in measured["repetitions"]
        ),
        "crash_safety": recovery["cases"] >= 100
        and all(
            record["exit_code"] == 91
            and record["visible_after_restart"] == record["previous_dataset"]
            for record in recovery["results"]
        ),
        "analytics": analytics["datasets"] >= 1000
        and len(analytics["cases"]) == analytics["datasets"],
        "models_evaluation": synthetic["system_correctness"]
        and public["frozen_verification"]
        and all(
            row["required_models_present"]
            and row["frozen_valid"]
            and row["data_integrity"]["valid"]
            for row in research_audit["runs"]
        )
        and research_audit["runs"][0]["cohort_irt_fitted"],
        "fitting_benchmark": len(measured.get("fit_repetitions", [])) >= 15
        and all(
            row["fitted_skills"] >= 2 and row["learners"] == 8
            for row in measured.get("fit_repetitions", [])
        ),
        "leakage": research_audit["planted_leaks_detected"]
        and all(
            row["fit_scopes_valid"] and row["split_audits_valid"] for row in research_audit["runs"]
        ),
        "real_data": public["rows"] >= 200000 and public["learners"] >= 1000,
        "simulation": simulation["seeds_per_policy_regime"] >= 30
        and len(simulation["regimes"]) >= 4
        and len(simulation["experiments"]) == 8
        and simulation["outcomes"] >= 1200
        and simulation["trajectories"] > 0,
        "product": browser["passed"] and len(browser["workflows"]) >= 8,
        "size": census["minimum_met"],
    }


def audit_research(catalog: Catalog, identifiers: list[str]) -> dict[str, Any]:
    runs = []
    probes = {}
    required = {
        "global",
        "item_prior",
        "recent",
        "hierarchical",
        "bkt",
        "irt1",
        "irt2",
        "logistic_without_skills",
        "logistic_without_time",
        "hierarchical_without_shrinkage",
        "bkt_forgetting",
        "bkt_mean_skills",
    }
    for identifier in identifiers:
        artifact = catalog.artifact(identifier)
        root = catalog.root / "artifacts" / identifier
        report = read(root / "report.json")
        rows = scan_events(catalog, artifact["dataset_id"]).collect().to_dicts()
        scopes_valid = splits_valid = True
        for index, fold in enumerate(report["folds"]):
            split = SplitManifest(**read(root / f"fold-{index}/split.json"))
            split_check = audit_split(rows, split)
            splits_valid = splits_valid and split_check["valid"]
            preprocessing = read(root / f"fold-{index}/preprocessing.json")
            checked = audit_preprocessing_manifest(preprocessing, split.assignments, split.hash)
            scopes_valid = scopes_valid and checked["valid"]
            if not probes:
                test_identity = next(
                    key for key, value in split.assignments.items() if value == "test"
                )

                def reject(name, operation):
                    try:
                        operation()
                    except ValueError as error:
                        probes[name] = {"detected": True, "reason": str(error)}
                    else:
                        raise ValueError(f"Deliberately planted leakage escaped detection: {name}")

                reject("future_target_feature", lambda: audit_feature_names({"future_correct": 1}))
                reject(
                    "current_unit_dependency",
                    lambda: audit_dependencies("target", ["future"], {"target": 0, "future": 1}),
                )
                reject(
                    "test_preprocessing_overlap",
                    lambda: audit_fit_scope(
                        FitScope("vocabulary", "train", (test_identity,), split.hash),
                        split.assignments,
                    ),
                )
                overlap = dict(split.assignments)
                first_train = next(key for key, value in overlap.items() if value == "train")
                overlap[test_identity] = "train"
                overlap[first_train] = "test"
                reject(
                    "overlapping_temporal_split",
                    lambda: audit_split(
                        rows, SplitManifest(overlap, split.mode, split.seed, split.parameters)
                    ),
                )
                probes["prefix_invariance"] = prefix_invariance(rows[:1000], 0)
        names = set(report["folds"][0]["models"])
        models = report["folds"][0]["models"]
        runs.append(
            {
                "artifact_id": identifier,
                "dataset_id": artifact["dataset_id"],
                "required_models_present": required.issubset(names)
                and bool(report["folds"][0]["selected_logistic"]),
                "fit_scopes_valid": scopes_valid,
                "split_audits_valid": splits_valid,
                "frozen_valid": evaluate_frozen(catalog, identifier)["valid"],
                "cohort_irt_fitted": all(models[name]["eligible"] for name in ["irt1", "irt2"]),
                "data_integrity": dataset_audit(
                    catalog, artifact["dataset_id"], verify_checksums=True
                ),
            }
        )
    return {
        "runs": runs,
        "probes": probes,
        "planted_leaks_detected": bool(probes)
        and all(value.get("detected", value.get("valid", False)) for value in probes.values()),
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
    public = read(destination / "research/public.json")
    synthetic = read(destination / "synthetic/synthetic.json")
    rechecked = audit_research(
        catalog, [public["artifact_id"], *[row["artifact_id"] for row in synthetic["datasets"]]]
    )
    if rechecked != read(destination / "research-audit.json"):
        errors.append("Recomputed data, split, fitting scope, or frozen prediction audits differ")
    census_process = subprocess.run(
        [sys.executable, str(Path(__file__).parents[3] / "scripts/count_production.py")],
        capture_output=True,
        text=True,
        check=True,
    )
    if json.loads(census_process.stdout) != read(destination / "private-census.json"):
        errors.append("Source and test census differs from actual authored files")
    for path in (root / "benchmark/corpora").glob("*.manifest.json"):
        manifest = read(path)
        source = path.with_suffix("").with_suffix(".ndjson")
        if not source.is_file() or file_hash(source) != manifest["sha256"]:
            errors.append(f"Benchmark corpus is missing or changed: {source.name}")
    gates = assess(root, read(destination / "private-census.json"))
    if gates != result["gates"] or not all(gates.values()):
        errors.append("Required gates are incomplete or disagree with immutable evidence")
    if digest(read(destination / "source-manifest.json")["files"]) != result["source_hash"]:
        errors.append("Source snapshot manifest was altered")
    if errors:
        raise ValueError("Evidence verification failed: " + "; ".join(errors))
    return {"valid": True, "path": str(path), "gates": gates, "regenerated": False}
