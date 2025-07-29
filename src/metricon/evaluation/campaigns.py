from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from metricon.analytics.engine import Analytics
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.pipeline import import_file, reconcile
from metricon.storage.artifacts import ArtifactWriter, verify_artifact
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json, file_hash
from metricon.storage.query import scan_events


def fixture_row(index: int, correct: bool, learner: str = "u") -> dict[str, Any]:
    return {
        "source_namespace": "campaign",
        "event_id": str(index),
        "learner_id": learner,
        "question_id": f"question-{index % 7}",
        "source_sequence": index,
        "skills": [f"skill-{index % 3}"],
        "correct": correct,
        "attempt_kind": "practice",
    }


def generated_ingestion(destination: Path, cases: int = 10000, seed: int = 2026) -> dict[str, Any]:
    if cases < 10000:
        raise ValueError("Generated import campaign requires at least 10000 cases")
    destination.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    records = []
    counts = {"accepted": 0, "duplicates": 0, "conflicts": 0, "rejected": 0, "received": cases}
    reference = {}
    for index in range(cases):
        kind = rng.randrange(10)
        identifier = rng.randrange(max(1, index // 2 + 1)) if kind < 3 else index
        value = fixture_row(identifier, bool(rng.randrange(2)), f"learner-{identifier % 31}")
        value["question_id"] = ["quoted,question", "中文.ε", "café", "=literal"][identifier % 4]
        value["source_sequence"] = identifier % 97
        if kind == 3:
            value["correct"] = "false"
        identity = (value["source_namespace"], value["event_id"])
        if kind == 4 and reference:
            identity = rng.choice(list(reference))
            value = dict(reference[identity])
        records.append(value)
        if type(value["correct"]) is not bool:
            counts["rejected"] += 1
        elif identity in reference:
            counts["duplicates" if reference[identity] == value else "conflicts"] += 1
        else:
            reference[identity] = value
            counts["accepted"] += 1
    source = destination / "cases.ndjson"
    source.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n")
    catalog = Catalog(destination / "store")
    workspace = catalog.create_workspace("Generated adversarial corpus", "synthetic")
    result = import_file(
        catalog, workspace["id"], source, AdapterOptions("ndjson", "campaign"), chunk_size=127
    )
    actual_counts = {key: result["report"][key] for key in counts}
    if actual_counts != counts:
        raise AssertionError({"expected": counts, "actual": actual_counts})
    actual = scan_events(catalog, result["dataset_id"]).collect().to_dicts()
    for row in actual:
        expected = reference[(row["source_namespace"], row["event_id"])]
        for key in expected:
            if row[key] != expected[key]:
                raise AssertionError(
                    {
                        "identity": row["identity"],
                        "field": key,
                        "expected": expected[key],
                        "actual": row[key],
                    }
                )
    retry = import_file(catalog, workspace["id"], source, AdapterOptions("ndjson", "campaign"))
    if not retry["duplicate_import"] or len(actual) != len(reference):
        raise AssertionError("Import retry changed the normalized corpus")
    report = {
        "cases": cases,
        "seed": seed,
        "counts": actual_counts,
        "reference_counts": counts,
        "source_sha256": file_hash(source),
        "dataset_id": result["dataset_id"],
        "retry_idempotent": True,
        "comparison": "Independent dictionary of logical input records; every accepted field compared against normalized Parquet",
        "normalized_identity_hash": hashlib.sha256(
            "\n".join(sorted(row["identity"] for row in actual)).encode()
        ).hexdigest(),
    }
    atomic_json(destination / "ingestion.json", report)
    return report


def generated_analytics(
    destination: Path, datasets: int = 1000, seed: int = 2026
) -> dict[str, Any]:
    if datasets < 1000:
        raise ValueError("Analytical campaign requires at least 1000 generated datasets")
    destination.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    results = []
    for case in range(datasets):
        catalog = Catalog(destination / "stores" / str(case))
        workspace = catalog.create_workspace(f"Generated analytical case {case}", "synthetic")
        values = []
        size = 1 + case % 37
        for index in range(size):
            value = fixture_row(index, bool(rng.randrange(2)), f"u-{index % 3}")
            if case % 3 == 0:
                value.update(
                    {
                        "timestamp": (
                            datetime(2026, 1, 1, tzinfo=timezone.utc)
                            + timedelta(seconds=index // 2)
                        ).isoformat(),
                        "time_semantics": "real",
                    }
                )
            if case % 4 == 0:
                value.update({"duration_ms": float(index * 1000), "duration_scope": "event"})
            values.append(value)
        shuffled = values[:]
        rng.shuffle(shuffled)
        source = destination / "current.ndjson"
        source.write_text("\n".join(json.dumps(row) for row in shuffled))
        imported = import_file(
            catalog, workspace["id"], source, AdapterOptions("ndjson", "campaign"), chunk_size=7
        )
        analytics = Analytics(catalog, imported["dataset_id"])
        result = analytics.overview()
        successes = sum(row["correct"] for row in values)
        groups = {}
        first = {}
        retries = {}
        for row in values:
            key = (row["learner_id"], row["question_id"])
            first.setdefault(key, row["correct"])
            groups.setdefault(row["question_id"], [0, 0])
            groups[row["question_id"]][0] += 1
            groups[row["question_id"]][1] += int(row["correct"])
            history = retries.setdefault(key, [])
            history.append(row["correct"])
        retry_values = [history.index(True) for history in retries.values() if True in history]
        if (
            result["accuracy"]["n"] != size
            or result["accuracy"]["successes"] != successes
            or result["first_attempt_accuracy"]["successes"] != sum(first.values())
        ):
            raise AssertionError({"case": case, "reference_n": size, "actual": result})
        if result["retries"]["solved"] != len(retry_values):
            raise AssertionError("Retry censoring disagrees with independent histories")
        actual_groups = analytics.groups("question", limit=100)["rows"]
        for group in actual_groups:
            if [group["accuracy"]["n"], group["accuracy"]["successes"]] != groups[group["id"]]:
                raise AssertionError("SQL group aggregate differs from Python reference")
        lazy = (
            scan_events(catalog, imported["dataset_id"])
            .select(__import__("polars").col("correct").sum())
            .collect()
            .item()
        )
        if lazy != successes:
            raise AssertionError("Polars aggregate differs from independent reference")
        results.append(
            {
                "case": case,
                "n": size,
                "successes": successes,
                "first_n": len(first),
                "first_successes": sum(first.values()),
                "source_sha256": file_hash(source),
                "dataset_id": imported["dataset_id"],
            }
        )
        shutil.rmtree(catalog.root)
    report = {
        "datasets": datasets,
        "seed": seed,
        "cases": results,
        "boundary_cases": [
            "single event",
            "all correct",
            "all incorrect",
            "timestamp ties",
            "out-of-order arrivals",
            "missing duration",
            "zero known duration",
            "censored retries",
        ],
        "comparison": "SQL and Polars aggregates versus independent ordered Python histories",
    }
    atomic_json(destination / "analytics.json", report)
    return report


def interruption_worker(request: dict[str, Any]) -> None:
    catalog = Catalog(Path(request["store"]))
    phase = request["phase"]

    def fault(current: str) -> None:
        if current == phase:
            os._exit(91)

    if request["kind"] == "import":
        import_file(
            catalog,
            request["workspace_id"],
            Path(request["source"]),
            AdapterOptions("ndjson", "campaign"),
            chunk_size=1,
            fault=fault,
        )
    else:
        with ArtifactWriter(
            catalog, "interruption-probe", request["dataset_id"], fault=fault
        ) as writer:
            atomic_json(
                writer.path / "result.json",
                {"case": request["case"], "dataset_id": request["dataset_id"]},
            )
            writer.publish({"case": request["case"]})


def interruption_campaign(destination: Path, cases: int = 100) -> dict[str, Any]:
    if cases < 100:
        raise ValueError("Crash recovery requires at least 100 actual process interruptions")
    destination.mkdir(parents=True, exist_ok=True)
    phases = ["after_partitions", "before_rename", "after_rename", "before_commit"]
    artifact_phases = ["before_manifest", "before_rename", "after_rename", "after_catalog"]
    evidence = []
    for case in range(cases):
        catalog = Catalog(destination / "stores" / str(case))
        workspace = catalog.create_workspace("Interruption probe", "synthetic")
        source = catalog.root / "first.ndjson"
        source.write_text(json.dumps(fixture_row(0, True)))
        initial = import_file(
            catalog, workspace["id"], source, AdapterOptions("ndjson", "campaign")
        )
        source = catalog.root / "next.ndjson"
        source.write_text(json.dumps(fixture_row(case + 1, False)))
        kind = "import" if case % 2 == 0 else "artifact"
        phase = (phases if kind == "import" else artifact_phases)[(case // 2) % 4]
        request = {
            "store": str(catalog.root),
            "workspace_id": workspace["id"],
            "source": str(source),
            "dataset_id": initial["dataset_id"],
            "kind": kind,
            "phase": phase,
            "case": case,
        }
        request_file = destination / "current-request.json"
        atomic_json(request_file, request)
        with (destination / f"interruption-{case}.log").open("w") as log:
            process = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import json,sys;from metricon.evaluation.campaigns import interruption_worker;interruption_worker(json.load(open(sys.argv[1])))",
                    str(request_file),
                ],
                stdout=log,
                stderr=log,
            )
        if process.returncode != 91:
            raise AssertionError(f"Interruption did not reach requested publication phase: {case}")
        reconciled = reconcile(catalog)
        visible = catalog.workspace(workspace["id"])["dataset_id"]
        if visible != initial["dataset_id"]:
            raise AssertionError("Interrupted import exposed a partial dataset")
        if len(scan_events(catalog, visible).collect()) != 1:
            raise AssertionError("Old committed corpus changed during interruption")
        for artifact in catalog.artifacts(visible):
            if not verify_artifact(catalog, artifact["id"])["valid"]:
                raise AssertionError("Partially committed artifact survived restart")
        if kind == "import":
            retry = import_file(
                catalog, workspace["id"], source, AdapterOptions("ndjson", "campaign")
            )
            if catalog.dataset(retry["dataset_id"])["row_count"] != 2:
                raise AssertionError("Restart retry failed to publish the complete new corpus")
        evidence.append(
            {
                "case": case,
                "kind": kind,
                "phase": phase,
                "exit_code": process.returncode,
                "reconciled": reconciled,
                "previous_dataset": initial["dataset_id"],
                "visible_after_restart": visible,
                "committed_artifacts": len(catalog.artifacts(visible)),
            }
        )
    report = {
        "cases": cases,
        "mechanism": "Actual subprocess os._exit at publication boundaries, followed by restart reconciliation and retry",
        "results": evidence,
    }
    atomic_json(destination / "recovery.json", report)
    return report
