from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from metricon import __version__
from metricon.analytics.engine import Analytics
from metricon.analytics.exports import export_dataset
from metricon.evaluation.comparison import compare_runs
from metricon.evaluation.frozen import evaluate_frozen
from metricon.ingest.validation import validate_file
from metricon.evaluation.experiment import ExperimentConfig, run_experiment
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.demo import demo_workspace
from metricon.ingest.ednet import create_subset, download_ednet
from metricon.ingest.pipeline import import_file, preview, reconcile
from metricon.quality.audit import dataset_audit
from metricon.recommendation.planner import PlannerConfig, plan
from metricon.simulation.engine import SimulationConfig, simulate
from metricon.storage.artifacts import verify_artifact
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="metricon", description="Local reproducible learning analytics laboratory"
    )
    result.add_argument("--root", type=Path, default=Path(".metricon"))
    result.add_argument("--version", action="version", version=__version__)
    commands = result.add_subparsers(dest="command", required=True)
    workspace = commands.add_parser("workspace")
    workspace.add_argument("name")
    workspace.add_argument("--kind", choices=["user", "research"], default="user")
    commands.add_parser("workspaces")
    for name in ["import", "ingest", "preview", "validate"]:
        command = commands.add_parser(name)
        command.add_argument("file", type=Path)
        command.add_argument(
            "--format", choices=["legacy", "csv", "ndjson", "json", "parquet"], required=True
        )
        command.add_argument("--namespace", default="local")
        command.add_argument("--learner", default="local-learner")
        if name in {"import", "ingest"}:
            command.add_argument("--workspace", required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--seed", type=int, default=2026)
    demo.add_argument("--learners", type=int, default=50)
    demo.add_argument("--attempts", type=int, default=60)
    for name in ["overview", "analyze", "audit", "experiment", "train"]:
        command = commands.add_parser(name)
        command.add_argument("dataset")
        if name in {"overview", "analyze"}:
            command.add_argument("--learner")
        if name == "audit":
            command.add_argument("--checksums", action="store_true")
        if name in {"experiment", "train"}:
            command.add_argument(
                "--split", choices=["forward", "learner", "rolling"], default="forward"
            )
            command.add_argument("--seed", type=int, default=2026)
            command.add_argument("--bootstrap", type=int, default=200)
            command.add_argument("--bkt-starts", type=int, default=3)
            command.add_argument("--no-ablations", action="store_true")
            command.add_argument("--frozen-state", action="store_true")
            command.add_argument(
                "--families",
                nargs="+",
                default=[
                    "global",
                    "item_prior",
                    "recent",
                    "logistic",
                    "hierarchical",
                    "bkt",
                    "irt1",
                    "irt2",
                ],
            )
    ednet = commands.add_parser("ednet")
    ednet.add_argument("action", choices=["download", "subset", "research"])
    ednet.add_argument("--seed", type=int, default=2026)
    ednet.add_argument("--interactions", type=int, default=200000)
    ednet.add_argument("--learners", type=int, default=1000)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    commands.add_parser("reconcile")
    verify = commands.add_parser("verify-artifact")
    verify.add_argument("artifact")
    simulation = commands.add_parser("simulate")
    simulation.add_argument("--config", type=Path)
    simulation.add_argument("--output", type=Path)
    planner = commands.add_parser("plan", aliases=["recommend"])
    planner.add_argument("dataset")
    planner.add_argument("learner")
    planner.add_argument("--budget", type=float, default=900)
    planner.add_argument("--run")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("artifact")
    compare = commands.add_parser("compare")
    compare.add_argument("left")
    compare.add_argument("right")
    compare.add_argument("--left-model", default="bkt")
    compare.add_argument("--right-model", default="global")
    export = commands.add_parser("export")
    export.add_argument("dataset")
    export.add_argument("--format", choices=["json", "csv", "parquet", "ndjson"], default="json")
    export.add_argument("--output", type=Path)
    commands.add_parser("benchmark")
    commands.add_parser("acceptance")
    commands.add_parser("verify")
    return result


def main() -> None:
    arguments = parser().parse_args()
    try:
        result = execute(arguments)
        if result is not None:
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
            if isinstance(result, dict) and result.get("valid") is False:
                raise SystemExit(1)
    except (ValueError, KeyError, RuntimeError) as error:
        print(f"metricon: {error}", file=sys.stderr)
        raise SystemExit(1) from error


def execute(arguments: argparse.Namespace) -> Any:
    catalog = Catalog(arguments.root)
    name = arguments.command
    if name == "workspace":
        return catalog.create_workspace(arguments.name, arguments.kind)
    if name == "workspaces":
        return catalog.workspaces()
    if name in {"import", "ingest", "preview", "validate"}:
        options = AdapterOptions(arguments.format, arguments.namespace, arguments.learner)
        if name == "validate":
            return validate_file(arguments.file, options)
        if name == "preview":
            return preview(arguments.file, options)
        return import_file(catalog, arguments.workspace, arguments.file, options)
    if name == "demo":
        return demo_workspace(catalog, arguments.seed, arguments.learners, arguments.attempts)
    if name in {"overview", "analyze"}:
        return Analytics(catalog, arguments.dataset).overview(arguments.learner)
    if name == "audit":
        return dataset_audit(catalog, arguments.dataset, arguments.checksums)
    if name in {"experiment", "train"}:
        config = ExperimentConfig(
            seed=arguments.seed,
            split=arguments.split,
            bootstrap_repetitions=arguments.bootstrap,
            bkt_starts=arguments.bkt_starts,
            online_updates=not arguments.frozen_state,
            ablations=not arguments.no_ablations,
            families=tuple(arguments.families),
        )
        identifier = run_experiment(
            catalog,
            arguments.dataset,
            config,
            progress=lambda _, message: print(message, file=sys.stderr),
        )
        return {"artifact_id": identifier, "path": str(catalog.root / "artifacts" / identifier)}
    if name == "ednet":
        cache = catalog.root / "cache"
        if arguments.action == "download":
            return {kind: download_ednet(cache, kind) for kind in ["contents", "kt1"]}
        subset = cache / "subset.ndjson"
        manifest = create_subset(
            cache / "EdNet-KT1.zip",
            cache / "contents.zip",
            subset,
            arguments.interactions,
            arguments.learners,
            arguments.seed,
        )
        if arguments.action == "subset":
            return manifest
        workspace = catalog.create_workspace("EdNet KT1 complete learner subset", "research")
        imported = import_file(
            catalog, workspace["id"], subset, AdapterOptions("ndjson", "ednet-kt1")
        )
        identifier = run_experiment(
            catalog,
            imported["dataset_id"],
            ExperimentConfig(seed=arguments.seed),
            progress=lambda _, message: print(message, file=sys.stderr),
        )
        return {
            "subset": {key: value for key, value in manifest.items() if key != "selected"},
            "workspace": catalog.workspace(workspace["id"]),
            "artifact_id": identifier,
        }
    if name == "serve":
        import uvicorn
        from metricon.api.app import Settings, create_app

        uvicorn.run(create_app(Settings(catalog.root)), host="127.0.0.1", port=arguments.port)
        return None
    if name == "reconcile":
        return reconcile(catalog)
    if name == "verify-artifact":
        return verify_artifact(catalog, arguments.artifact)
    if name in {"plan", "recommend"}:
        return plan(
            catalog,
            arguments.dataset,
            arguments.learner,
            PlannerConfig(budget_seconds=arguments.budget, model_artifact_id=arguments.run),
        )
    if name == "simulate":
        values = json.loads(arguments.config.read_text()) if arguments.config else {}
        result = simulate(SimulationConfig(**values))
        if arguments.output:
            atomic_json(arguments.output, result)
            return {"output": str(arguments.output), "simulation_hash": result["simulation_hash"]}
        return result
    if name == "evaluate":
        return evaluate_frozen(catalog, arguments.artifact)
    if name == "compare":
        return compare_runs(
            catalog, arguments.left, arguments.right, arguments.left_model, arguments.right_model
        )
    if name == "export":
        import shutil

        identifier = export_dataset(catalog, arguments.dataset, arguments.format)
        path = catalog.root / "artifacts" / identifier / f"events.{arguments.format}"
        if arguments.output:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, arguments.output)
        return {
            "artifact_id": identifier,
            "dataset_id": arguments.dataset,
            "path": str(arguments.output or path),
        }
    if name == "benchmark":
        from metricon.evaluation.benchmark import benchmark

        summary = benchmark(catalog.root / "benchmark")
        return {
            "path": str(catalog.root / "benchmark/benchmark.json"),
            "workloads": list(summary["summaries"]),
        }
    if name in {"acceptance", "verify"}:
        from metricon.evaluation.acceptance import acceptance, verify_evidence

        return acceptance(catalog.root) if name == "acceptance" else verify_evidence(catalog.root)
    raise ValueError("Unsupported command")


if __name__ == "__main__":
    main()
