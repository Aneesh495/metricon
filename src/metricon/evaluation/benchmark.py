from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from threadpoolctl import threadpool_info

from metricon.evaluation.workloads import reference_checksum, write_workload
from metricon.evaluation.experiment import environment
from metricon.features.materialize import materialize_history
from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.pipeline import import_file
from metricon.models.baselines import GlobalBaseline
from metricon.models.bkt import BKT
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json
from metricon.storage.lineage import source_code_hash
from metricon.storage.query import analytical_connection
from metricon.storage.hashing import file_hash

QUERIES = {
    "accuracy": "SELECT count(*) n,sum(correct::INTEGER) successes,sum(source_sequence) index_sum FROM events",
    "question_groups": "SELECT question_id,count(*) n,sum(correct::INTEGER) successes FROM events GROUP BY question_id ORDER BY question_id",
    "skill_groups": "SELECT skill,count(*) n,sum(correct::INTEGER) successes FROM (SELECT correct,unnest(skills) skill FROM events) GROUP BY skill ORDER BY skill",
    "learner_history": "SELECT event_id,correct,source_sequence FROM events WHERE learner_id='learner-42' ORDER BY source_sequence LIMIT 100",
}


def measurement_sources(repository: Path) -> dict[str, str]:
    package = repository / "src/metricon"
    paths = [
        *package.joinpath("ingest").glob("*.py"),
        *package.joinpath("schema").glob("*.py"),
        *package.joinpath("storage").glob("*.py"),
        package / "features/history.py",
        package / "features/materialize.py",
        *package.joinpath("models").glob("*.py"),
    ]
    return {path.relative_to(package).as_posix(): file_hash(path) for path in sorted(paths)}


def peak_rss() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def fit_worker(request: dict[str, Any]) -> dict[str, Any]:
    catalog = Catalog(Path(request["store"]), read_only=True)
    dataset = request["dataset_id"]
    identifiers = [f"learner-{index}" for index in [42, 43, 52, 53, 62, 63, 72, 73]]
    with analytical_connection(catalog, dataset) as connection:
        count = connection.execute(
            "SELECT count(*) FROM events WHERE learner_id IN (SELECT unnest(?))", [identifiers]
        ).fetchone()[0]
        if count > 10000:
            raise ValueError("Fitting benchmark exceeds its complete-history input bound")
        rows = (
            connection.execute(
                "SELECT * FROM events WHERE learner_id IN (SELECT unnest(?)) ORDER BY learner_id,source_sequence",
                [identifiers],
            )
            .fetch_arrow_table()
            .to_pylist()
        )
    timings = {}
    parameters = {}
    diagnostics = {}
    for name, model in [("global", GlobalBaseline()), ("bkt", BKT(starts=2, max_iterations=80))]:
        started = time.perf_counter()
        model.fit(rows)
        timings[name] = time.perf_counter() - started
        parameters[name] = model.parameters()
        diagnostics[name] = getattr(model, "diagnostics", {})
    fitted = sum(item.get("fitted", False) for item in diagnostics["bkt"].values())
    if fitted < 2 or len({row["learner_id"] for row in rows}) != 8:
        raise ValueError(
            "Benchmark must optimize two supported skills from eight complete histories"
        )
    repository = Path(__file__).parents[3]
    snapshot = source_code_hash(repository / "src/metricon")
    directory = Path(request["snapshot_root"]) / snapshot["hash"]
    directory.mkdir(parents=True, exist_ok=True)
    for name, checksum in snapshot["files"].items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository / "src/metricon" / name, target)
        if file_hash(target) != checksum:
            raise RuntimeError("Fitting source changed during snapshot")
    locked = environment(repository / "uv.lock")
    atomic_json(directory / "manifest.json", snapshot)
    atomic_json(directory / "environment.json", locked)
    shutil.copyfile(repository / "uv.lock", directory / "uv.lock")
    return {
        "contract": "complete-eight-history-fit/1",
        "input_rows": request["rows"],
        "repetition": request["repetition"],
        "dataset_id": dataset,
        "fitting_rows": len(rows),
        "learners": len(identifiers),
        "learner_ids": identifiers,
        "fitted_skills": fitted,
        "fit_seconds": timings,
        "parameters": parameters,
        "diagnostics": diagnostics,
        "peak_process_rss_bytes": peak_rss(),
        "source_code": snapshot,
        "environment": locked,
        "native_thread_pools": threadpool_info(),
        "scope": "Eight fixed complete learner histories, at most 10000 accepted rows. Timings exclude query, process startup and source snapshot IO.",
    }


def fitting_benchmark(root: Path, sizes: tuple[int, ...], repetitions: int) -> list[dict[str, Any]]:
    destination = root / "fitting"
    destination.mkdir(exist_ok=True)
    records = []
    source_hash = source_code_hash(Path(__file__).parents[1])["hash"]
    for size in sizes:
        store = root / "stores" / f"{size}-{repetitions - 1}"
        catalog = Catalog(store, read_only=True)
        dataset = catalog.workspaces()[-1]["dataset_id"]
        for index in range(repetitions):
            path = destination / f"fit-{size}-{index}.json"
            if path.exists() and json.loads(path.read_text())["source_code"]["hash"] != source_hash:
                archive = destination / "previous"
                archive.mkdir(exist_ok=True)
                path.rename(archive / f"{path.stem}-{time.time_ns()}.json")
            if not path.exists():
                request = destination / "request.json"
                atomic_json(
                    request,
                    {
                        "store": str(store.resolve()),
                        "dataset_id": dataset,
                        "rows": size,
                        "repetition": index,
                        "snapshot_root": str((root / "source-snapshots").resolve()),
                    },
                )
                with (destination / f"fit-{size}-{index}-{time.time_ns()}.log").open("w") as log:
                    subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "metricon.evaluation.benchmark",
                            "--fit-worker",
                            str(request),
                            "--output",
                            str(path),
                        ],
                        env={
                            **os.environ,
                            "OMP_NUM_THREADS": "1",
                            "OPENBLAS_NUM_THREADS": "1",
                            "MKL_NUM_THREADS": "1",
                            "POLARS_MAX_THREADS": "2",
                        },
                        stdout=log,
                        stderr=log,
                        check=True,
                    )
            records.append(json.loads(path.read_text()))
    return records


def measure_worker(request: dict[str, Any]) -> dict[str, Any]:
    store, source = Path(request["store"]), Path(request["source"])
    catalog = Catalog(store)
    repository = Path(__file__).parents[3]
    source_snapshot = source_code_hash(repository / "src/metricon")
    locked_environment = environment(repository / "uv.lock")
    snapshot = Path(request["snapshot_root"]) / source_snapshot["hash"]
    snapshot.mkdir(parents=True, exist_ok=True)
    for name in source_snapshot["files"]:
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository / "src/metricon" / name, target)
    atomic_json(snapshot / "manifest.json", source_snapshot)
    atomic_json(snapshot / "environment.json", locked_environment)
    shutil.copyfile(repository / "uv.lock", snapshot / "uv.lock")
    workspace = catalog.create_workspace("Streaming synthetic workload", "synthetic")
    started = time.perf_counter()
    result = import_file(
        catalog,
        workspace["id"],
        source,
        AdapterOptions("ndjson", "scale-synthetic"),
        chunk_size=65536,
    )
    import_seconds = time.perf_counter() - started
    import_peak = peak_rss()
    atomic_json(
        store / "import-measurement.json",
        {
            "seconds": import_seconds,
            "peak_rss_bytes": import_peak,
            "result": result,
            "source_code": source_snapshot,
            "environment": locked_environment,
        },
    )
    expected = request["corpus"]["reference_counts"]
    actual = {key: result["report"][key] for key in expected}
    if actual != expected:
        raise AssertionError({"expected": expected, "actual": actual})
    dataset = result["dataset_id"]
    queries = []
    reference = reference_checksum(request["rows"])
    for name, sql in QUERIES.items():
        with analytical_connection(catalog, dataset) as connection:
            for condition in ["connection-cold", "connection-warm"]:
                profile = store / f"profile-{name}-{condition}.json"
                connection.execute("PRAGMA enable_profiling='json'")
                connection.execute("SET profiling_output=?", (str(profile),))
                started = time.perf_counter()
                rows = connection.execute(sql).fetchall()
                seconds = time.perf_counter() - started
                connection.execute("PRAGMA disable_profiling")
                profiling = json.loads(profile.read_text())
                if (
                    name == "accuracy"
                    and dict(zip(["n", "successes", "index_sum"], rows[0])) != reference
                ):
                    raise AssertionError(
                        "Normalized aggregate content differs from independent workload arithmetic"
                    )
                queries.append(
                    {
                        "query": name,
                        "condition": condition,
                        "seconds": seconds,
                        "bytes_read": profiling["total_bytes_read"],
                        "rows_returned": len(rows),
                        "profile": profiling,
                    }
                )
    feature_start = time.perf_counter()
    features = materialize_history(catalog, dataset, store / "features.parquet", chunk_size=65536)
    feature_seconds = time.perf_counter() - feature_start
    with analytical_connection(catalog, dataset) as connection:
        fitting_rows = (
            connection.execute(
                "SELECT * FROM events WHERE learner_id IN ('learner-42','learner-43','learner-44','learner-45') ORDER BY learner_id,source_sequence LIMIT 10000"
            )
            .fetch_arrow_table()
            .to_pylist()
        )
    fit_times = {}
    for name, model in [
        ("global", GlobalBaseline()),
        ("bkt", BKT(starts=2, max_iterations=80)),
    ]:
        started = time.perf_counter()
        model.fit(fitting_rows)
        fit_times[name] = time.perf_counter() - started
    manifest = catalog.dataset(dataset)["manifest"]
    parquet_bytes = sum(
        (catalog.root / part["path"]).stat().st_size for part in manifest["partitions"]
    )
    return {
        "source_code": source_snapshot,
        "environment": locked_environment,
        "source_snapshot": str(snapshot),
        "rows": request["rows"],
        "repetition": request["repetition"],
        "source_sha256": request["corpus"]["sha256"],
        "source_bytes": source.stat().st_size,
        "counts": actual,
        "independent_content": reference,
        "dataset_id": dataset,
        "manifest": manifest,
        "import_seconds": import_seconds,
        "rows_per_second": request["rows"] / import_seconds,
        "peak_import_rss_bytes": import_peak,
        "peak_worker_rss_bytes": peak_rss(),
        "parquet_bytes": parquet_bytes,
        "queries": queries,
        "feature_seconds": feature_seconds,
        "features": features,
        "fit_seconds": fit_times,
        "fit_scope": {
            "rows": len(fitting_rows),
            "selection": "Four fixed learner histories, bounded at 10000 rows; never the full scale corpus",
        },
        "duckdb_threads": 2,
        "numeric_threads": 1,
        "native_thread_pools": threadpool_info(),
        "polars_threads": pl.thread_pool_size(),
        "cache_semantics": "Fresh worker and analytical connection for cold; OS page cache is not flushed. Warm repeats the query on its existing connection.",
    }


def benchmark(
    root: Path, sizes: tuple[int, ...] = (100000, 1000000, 10000000), repetitions: int = 5
) -> dict[str, Any]:
    if repetitions < 5:
        raise ValueError("Benchmark evidence requires at least five repetitions")
    root.mkdir(parents=True, exist_ok=True)
    records = []
    required_sources = measurement_sources(Path(__file__).parents[3])
    required_lock = environment(Path(__file__).parents[3] / "uv.lock")["lock_sha256"]
    for size in sizes:
        source = root / "corpora" / f"events-{size}.ndjson"
        corpus = write_workload(source, size)
        for repetition in range(repetitions):
            output = root / f"repetition-{size}-{repetition}.json"
            store = root / "stores" / f"{size}-{repetition}"
            previous = json.loads(output.read_text()) if output.exists() else None
            if previous is not None and (
                "native_thread_pools" not in previous
                or previous["environment"]["lock_sha256"] != required_lock
                or any(
                    previous["source_code"]["files"].get(name) != checksum
                    for name, checksum in required_sources.items()
                )
            ):
                archive = root / "previous"
                archive.mkdir(exist_ok=True)
                output.rename(archive / f"{output.stem}-{time.time_ns()}.json")
            if output.exists():
                result = json.loads(output.read_text())
            else:
                if store.exists():
                    failed = root / "failures" / f"{size}-{repetition}-{time.time_ns()}"
                    failed.mkdir(parents=True)
                    for item in store.rglob("*.json"):
                        target = failed / item.relative_to(store)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(item, target)
                    atomic_json(
                        failed / "cleanup.json",
                        {
                            "reason": "Previous worker failed before complete measurement; retain diagnostics and manifests, recreate an empty workload store",
                            "source_retained": str(source),
                        },
                    )
                    shutil.rmtree(store)
                request = root / "current-request.json"
                atomic_json(
                    request,
                    {
                        "store": str(store.resolve()),
                        "source": str(source.resolve()),
                        "corpus": corpus,
                        "rows": size,
                        "repetition": repetition,
                        "snapshot_root": str((root / "source-snapshots").resolve()),
                    },
                )
                worker_environment = {
                    **os.environ,
                    "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1",
                    "POLARS_MAX_THREADS": "2",
                }
                log_path = root / f"worker-{size}-{repetition}-{time.time_ns()}.log"
                with log_path.open("w") as log:
                    subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "metricon.evaluation.benchmark",
                            "--worker",
                            str(request),
                            "--output",
                            str(output),
                        ],
                        env=worker_environment,
                        stdout=log,
                        stderr=log,
                        check=True,
                    )
                result = json.loads(output.read_text())
            records.append(result)
            print(
                f"Benchmark {size} repetition {repetition + 1}: {result['rows_per_second']:.0f} rows/s",
                flush=True,
            )
            if repetition < repetitions - 1 and store.exists():
                shutil.rmtree(store)
    summary = {
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "python": sys.version,
        },
        "repetitions": records,
        "summaries": {},
        "measurements_are_promises": False,
    }
    summary["fit_repetitions"] = fitting_benchmark(root, sizes, repetitions)
    hardware_path = root / "hardware.json"
    if hardware_path.exists():
        summary["hardware"]["observed_profile"] = json.loads(hardware_path.read_text())
    elif sys.platform == "darwin":
        try:
            summary["hardware"]["cpu_model"] = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip()
            summary["hardware"]["memory_bytes"] = int(
                subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            )
        except (subprocess.CalledProcessError, ValueError) as error:
            summary["hardware"]["hardware_query_error"] = str(error)
    elif hasattr(os, "sysconf"):
        summary["hardware"]["memory_bytes"] = os.sysconf("SC_PAGE_SIZE") * os.sysconf(
            "SC_PHYS_PAGES"
        )
    if not hardware_path.exists():
        atomic_json(
            hardware_path,
            {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "method": "Runtime platform and host system queries",
                "profile": summary["hardware"],
            },
        )
    for size in sizes:
        selected = [record for record in records if record["rows"] == size]
        rates = [record["rows_per_second"] for record in selected]
        queries = {}
        for name in QUERIES:
            for condition in ["connection-cold", "connection-warm"]:
                values = [
                    query["seconds"]
                    for record in selected
                    for query in record["queries"]
                    if query["query"] == name and query["condition"] == condition
                ]
                queries[f"{name}/{condition}"] = {
                    "p50_seconds": float(np.median(values)),
                    "p95_seconds": float(np.quantile(values, 0.95)),
                    "repetitions": len(values),
                }
        summary["summaries"][str(size)] = {
            "median_rows_per_second": float(np.median(rates)),
            "maximum_import_rss_bytes": max(record["peak_import_rss_bytes"] for record in selected),
            "queries": queries,
        }
    atomic_json(root / "benchmark.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--fit-worker", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--root", type=Path, default=Path(".metricon/benchmark"))
    arguments = parser.parse_args()
    if arguments.fit_worker:
        atomic_json(arguments.output, fit_worker(json.loads(arguments.fit_worker.read_text())))
    elif arguments.worker:
        atomic_json(arguments.output, measure_worker(json.loads(arguments.worker.read_text())))
    else:
        benchmark(arguments.root)
