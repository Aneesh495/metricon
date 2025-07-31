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
from pathlib import Path
from typing import Any

import numpy as np

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

QUERIES = {
    "accuracy": "SELECT count(*) n,sum(correct::INTEGER) successes,sum(source_sequence) index_sum FROM events",
    "question_groups": "SELECT question_id,count(*) n,sum(correct::INTEGER) successes FROM events GROUP BY question_id ORDER BY question_id",
    "skill_groups": "SELECT skill,count(*) n,sum(correct::INTEGER) successes FROM (SELECT correct,unnest(skills) skill FROM events) GROUP BY skill ORDER BY skill",
    "learner_history": "SELECT event_id,correct,source_sequence FROM events WHERE learner_id='learner-42' ORDER BY source_sequence LIMIT 100",
}


def peak_rss() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


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
        "cache_semantics": "Fresh worker and analytical connection for cold; OS page cache is not flushed. Warm repeats the query on its existing connection.",
    }


def benchmark(
    root: Path, sizes: tuple[int, ...] = (100000, 1000000, 10000000), repetitions: int = 5
) -> dict[str, Any]:
    if repetitions < 5:
        raise ValueError("Benchmark evidence requires at least five repetitions")
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for size in sizes:
        source = root / "corpora" / f"events-{size}.ndjson"
        corpus = write_workload(source, size)
        for repetition in range(repetitions):
            output = root / f"repetition-{size}-{repetition}.json"
            store = root / "stores" / f"{size}-{repetition}"
            if output.exists():
                result = json.loads(output.read_text())
            else:
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
                environment = {
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
                        env=environment,
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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--root", type=Path, default=Path(".metricon/benchmark"))
    arguments = parser.parse_args()
    if arguments.worker:
        atomic_json(arguments.output, measure_worker(json.loads(arguments.worker.read_text())))
    else:
        benchmark(arguments.root)
