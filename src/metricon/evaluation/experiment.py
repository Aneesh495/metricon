from __future__ import annotations

import importlib.metadata
import platform
import shutil
import resource
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from metricon.evaluation.calibration import PlattCalibrator
from metricon.evaluation.diagnostics import (
    distribution_shift,
    residual_diagnostics,
    sequence_error_profile,
)
from metricon.evaluation.metrics import cluster_intervals, metric_summary, paired_comparison
from metricon.evaluation.splits import (
    SplitManifest,
    audit_split,
    forward_split,
    learner_split,
    rolling_splits,
)
from metricon.features.history import FEATURE_VERSION, domain, labels, ordered_rows
from metricon.features.leakage import preprocessing_manifest
from metricon.models.base import save_model
from metricon.models.baselines import GlobalBaseline, ItemPrior, LogisticHistory, RecentHistory
from metricon.models.bkt import BKT
from metricon.models.hierarchical import HierarchicalBetaBinomial
from metricon.models.irt import IRT, IRTEligibilityError
from metricon.schema.events import digest, canonical_json
from metricon.storage.artifacts import ArtifactWriter
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json, file_hash
from metricon.storage.query import scan_events
from metricon.storage.lineage import register_experiment_lineage, source_code_hash


@dataclass(frozen=True)
class ExperimentConfig:
    seed: int = 2026
    split: str = "forward"
    bootstrap_repetitions: int = 200
    bkt_starts: int = 3
    bkt_max_iterations: int = 120
    online_updates: bool = True
    ablations: bool = True
    calibration: bool = True
    maximum_rows: int = 2_000_000
    families: tuple[str, ...] = (
        "global",
        "item_prior",
        "recent",
        "logistic",
        "hierarchical",
        "bkt",
        "irt1",
        "irt2",
    )
    logistic_candidates: tuple[float, ...] = (0.1, 1.0, 10.0)
    rolling_folds: int = 3

    def validate(self) -> None:
        if self.split not in {"forward", "learner", "rolling"}:
            raise ValueError("Unsupported split mode")
        if not 20 <= self.bootstrap_repetitions <= 5000:
            raise ValueError("Bootstrap repetitions must be 20..5000")
        if not 1 <= self.maximum_rows <= 5_000_000:
            raise ValueError("Training row bound must be 1..5000000")
        if not 1 <= self.bkt_starts <= 10 or not 1 <= self.bkt_max_iterations <= 500:
            raise ValueError("Invalid BKT fitting limits")
        known = {
            "global",
            "item_prior",
            "recent",
            "logistic",
            "hierarchical",
            "bkt",
            "irt1",
            "irt2",
        }
        if (
            not self.families
            or not set(self.families).issubset(known)
            or "global" not in self.families
        ):
            raise ValueError(
                "Experiment must include the global baseline and supported model families"
            )
        if (
            not self.logistic_candidates
            or len(self.logistic_candidates) > 10
            or any(c <= 0 for c in self.logistic_candidates)
        ):
            raise ValueError("Logistic candidates must be bounded positive values")

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


def environment(lock_path: Path | None = None) -> dict[str, Any]:
    if lock_path is None or not lock_path.exists():
        packaged = Path(__file__).parents[1] / "dependency.lock"
        lock_path = packaged if packaged.is_file() else lock_path
    packages = [
        "numpy",
        "polars",
        "pyarrow",
        "duckdb",
        "scipy",
        "scikit-learn",
        "pydantic",
        "fastapi",
    ]
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": {name: importlib.metadata.version(name) for name in packages},
        "lock_sha256": file_hash(lock_path) if lock_path and lock_path.exists() else None,
    }


def dependency_lock() -> Path:
    checkout = Path(__file__).parents[3] / "uv.lock"
    packaged = Path(__file__).parents[1] / "dependency.lock"
    for path in [checkout, packaged]:
        if path.is_file():
            return path
    raise ValueError(
        "Reproducible experiments require the dependency lock from the checkout or wheel"
    )


def model_factories(config: ExperimentConfig) -> dict[str, Callable[[], Any]]:
    factories: dict[str, Callable[[], Any]] = {}
    choices = {
        "global": GlobalBaseline,
        "item_prior": ItemPrior,
        "recent": RecentHistory,
        "hierarchical": HierarchicalBetaBinomial,
        "bkt": lambda: BKT(
            config.seed, config.bkt_starts, max_iterations=config.bkt_max_iterations
        ),
        "irt1": lambda: IRT(1),
        "irt2": lambda: IRT(2),
    }
    for name in config.families:
        if name in choices:
            factories[name] = choices[name]
    if "logistic" in config.families:
        for c in config.logistic_candidates:
            factories[f"logistic_c{c:g}"] = lambda c=c: LogisticHistory(c, config.seed)
    if config.ablations:
        if "logistic" in config.families:
            factories["logistic_without_skills"] = lambda: LogisticHistory(
                1, config.seed, skill_tags=False
            )
            factories["logistic_without_time"] = lambda: LogisticHistory(
                1, config.seed, temporal=False
            )
        if "hierarchical" in config.families:
            factories["hierarchical_without_shrinkage"] = lambda: HierarchicalBetaBinomial(
                shrinkage=False
            )
        if "bkt" in config.families:
            factories["bkt_forgetting"] = lambda: BKT(
                config.seed,
                config.bkt_starts,
                forgetting=True,
                max_iterations=config.bkt_max_iterations,
            )
            factories["bkt_mean_skills"] = lambda: BKT(
                config.seed,
                config.bkt_starts,
                multi_skill="mean",
                max_iterations=config.bkt_max_iterations,
            )
    return factories


def slice_metrics(
    rows: list[dict[str, Any]], p: np.ndarray, training: list[dict[str, Any]]
) -> dict[str, Any]:
    y = labels(rows)
    known_domains = {domain(row) for row in training}
    known_items = {(row["source_namespace"], row["question_id"]) for row in training}
    masks = {
        "cold_learner": np.asarray([domain(row) not in known_domains for row in rows]),
        "warm_learner": np.asarray([domain(row) in known_domains for row in rows]),
        "cold_item": np.asarray(
            [(row["source_namespace"], row["question_id"]) not in known_items for row in rows]
        ),
        "warm_item": np.asarray(
            [(row["source_namespace"], row["question_id"]) in known_items for row in rows]
        ),
        "untagged": np.asarray([not row["skills"] for row in rows]),
    }
    summaries = {name: metric_summary(y[mask], p[mask]) for name, mask in masks.items()}
    skills = sorted({skill for row in rows for skill in row["skills"]})
    summaries["skills"] = {}
    for skill in skills:
        mask = np.asarray([skill in row["skills"] for row in rows])
        summary = metric_summary(y[mask], p[mask])
        summaries["skills"][skill] = {
            key: summary[key]
            for key in ["n", "positives", "log_loss", "brier", "auroc", "accuracy"]
        }
    summaries["learners"] = {}
    learners = sorted({row["learner_id"] for row in rows})
    by_learner: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_learner.setdefault(row["learner_id"], []).append(index)
    for learner in learners:
        indices = np.asarray(by_learner[learner])
        summary = metric_summary(y[indices], p[indices])
        summaries["learners"][learner] = {
            key: summary[key] for key in ["n", "positives", "log_loss", "brier", "auroc"]
        }
    return summaries


def run_experiment(
    catalog: Catalog,
    dataset_id: str,
    config: ExperimentConfig,
    progress: Callable[[float, str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> str:
    config.validate()
    dataset = catalog.dataset(dataset_id)
    if dataset["row_count"] > config.maximum_rows:
        raise ValueError(
            "Dataset exceeds training memory bound; create a documented complete-learner subset first"
        )
    started = time.perf_counter()
    rows = ordered_rows(scan_events(catalog, dataset_id).collect().to_dicts())
    if config.split == "forward":
        manifests = [forward_split(rows, seed=config.seed)]
    elif config.split == "learner":
        manifests = [learner_split(rows, seed=config.seed)]
    else:
        manifests = rolling_splits(rows, config.rolling_folds, config.seed)
    report: dict[str, Any] = {
        "dataset_id": dataset_id,
        "configuration": config.as_dict(),
        "environment": environment(dependency_lock()),
        "feature_version": FEATURE_VERSION,
        "source_code": source_code_hash(Path(__file__).parents[1]),
        "folds": [],
        "interpretation": "Predictive comparisons are observational; study-policy effects require separate evidence.",
    }
    with ArtifactWriter(catalog, "experiment", dataset_id) as writer:
        source_directory = writer.path / "source"
        source_root = Path(__file__).parents[1]
        for relative, expected in report["source_code"]["files"].items():
            destination = source_directory / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_root / relative, destination)
            if file_hash(destination) != expected:
                raise RuntimeError(
                    "Reusable pipeline source changed while snapshotting the experiment"
                )
        atomic_json(writer.path / "source-manifest.json", report["source_code"])
        atomic_json(writer.path / "environment.json", report["environment"])
        shutil.copyfile(dependency_lock(), writer.path / "dependency.lock")
        if file_hash(writer.path / "dependency.lock") != report["environment"]["lock_sha256"]:
            raise RuntimeError("Dependency lock changed while snapshotting the experiment")
        atomic_json(
            writer.path / "feature-contract.json",
            {
                "version": FEATURE_VERSION,
                "code_hash": report["source_code"]["hash"],
                "history_policy": "Feature values precede target answer and its whole coupled unit",
                "vocabulary_policy": "Fit on training only; unseen evaluation categories ignored",
                "temporal_policy": "Within-known-domain gaps only; unknown timestamps remain missing",
                "scaling_policy": "Training-only max-absolute scaling retained in serialized logistic parameters",
            },
        )
        parents = {
            "pipeline-source": report["source_code"]["hash"],
            "environment": digest(report["environment"]),
        }
        for index, manifest in enumerate(manifests):
            if cancelled and cancelled():
                raise RuntimeError("Experiment cancelled before publication")
            fold_path = writer.path / f"fold-{index}"
            fold_path.mkdir()
            atomic_json(fold_path / "split.json", manifest.as_dict())
            atomic_json(
                fold_path / "preprocessing.json",
                preprocessing_manifest(manifest.assignments, manifest.hash),
            )
            parents[f"split-{index}"] = digest([dataset_id, manifest.hash])
            training = manifest.select(rows, "train")
            validation = manifest.select(rows, "validation")
            test = manifest.select(rows, "test")
            if not training or not validation or not test:
                raise ValueError("Split has an empty train, validation, or test partition")
            fold = _run_fold(
                training, validation, test, manifest, config, fold_path, progress, cancelled
            )
            report["folds"].append(fold)
        report["runtime_seconds"] = time.perf_counter() - started
        maximum_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report["peak_process_rss_bytes"] = int(
            maximum_rss if platform.system() == "Darwin" else maximum_rss * 1024
        )
        report["memory_method"] = (
            "Process lifetime peak RSS, including pre-run allocations; not isolated model memory"
        )
        atomic_json(writer.path / "report.json", report)
        markdown = render_report(report)
        (writer.path / "report.md").write_text(markdown, encoding="utf-8")
        identifier = writer.publish(
            {
                "configuration": config.as_dict(),
                "split_hashes": [m.hash for m in manifests],
                "data_hash": dataset_id,
                "feature_version": FEATURE_VERSION,
                "environment": report["environment"],
                "source_code_hash": report["source_code"]["hash"],
            },
            parents,
        )
    if not catalog.read_only:
        register_experiment_lineage(catalog, identifier)
    if progress:
        progress(1.0, "Experiment published with hashed predictions and report")
    return identifier


def _run_fold(
    training: list[dict[str, Any]],
    validation: list[dict[str, Any]],
    test: list[dict[str, Any]],
    manifest: SplitManifest,
    config: ExperimentConfig,
    path: Path,
    progress: Callable[[float, str], None] | None,
    cancelled: Callable[[], bool] | None,
) -> dict[str, Any]:
    models = model_factories(config)
    summaries: dict[str, Any] = {}
    predictions: dict[str, np.ndarray] = {}
    raw_rows = []
    y_validation, y_test = labels(validation), labels(test)
    learners = [canonical_json([row["source_namespace"], row["learner_id"]]) for row in test]
    for model_index, (name, factory) in enumerate(models.items()):
        if cancelled and cancelled():
            raise RuntimeError("Experiment cancelled before publication")
        if progress:
            progress(
                model_index / max(1, len(models)),
                f"Fitting {name}; test partition remains untouched during fitting",
            )
        model_started = time.perf_counter()
        model = factory()
        try:
            model.fit(training)
        except IRTEligibilityError as error:
            summaries[name] = {"eligible": False, "reason": str(error)}
            continue
        save_model(path / f"{name}.model.json", model)
        parameters_hash = digest(model.parameters())
        validation_prediction = model.predict(validation, update=config.online_updates)
        calibrator = PlattCalibrator()
        if config.calibration:
            calibrator.fit(y_validation, validation_prediction)
        atomic_json(path / f"{name}.calibration.json", calibrator.parameters())
        test_prediction = model.predict(test, update=config.online_updates)
        predictions[name] = test_prediction
        summary = {
            "eligible": True,
            "parameters_hash": parameters_hash,
            "validation": metric_summary(y_validation, validation_prediction),
            "test": metric_summary(y_test, test_prediction),
            "cluster_intervals": cluster_intervals(
                y_test, test_prediction, learners, config.bootstrap_repetitions, config.seed
            ),
            "slices": slice_metrics(test, test_prediction, training),
            "diagnostics": getattr(model, "diagnostics", {}),
            "runtime_seconds": time.perf_counter() - model_started,
            "residuals": residual_diagnostics(
                y_test, test_prediction, learners, config.seed, config.bootstrap_repetitions
            ),
            "sequence_error_profile": sequence_error_profile(test, test_prediction),
            "calibration_parameters": calibrator.parameters(),
        }
        if config.calibration:
            calibrated = calibrator.predict(test_prediction)
            predictions[name + "_calibrated"] = calibrated
            summary["calibrated_test"] = metric_summary(y_test, calibrated)
            summary["calibrated_cluster_intervals"] = cluster_intervals(
                y_test, calibrated, learners, config.bootstrap_repetitions, config.seed
            )
        summaries[name] = summary
        for partition, selected, values in [
            ("validation", validation, validation_prediction),
            ("test", test, test_prediction),
        ]:
            calibrated_values = (
                calibrator.predict(values) if config.calibration else [None] * len(values)
            )
            for row, value, calibrated_value in zip(selected, values, calibrated_values):
                raw_rows.append(
                    {
                        "identity": row["identity"],
                        "learner_id": row["learner_id"],
                        "source_namespace": row["source_namespace"],
                        "learner_cluster": canonical_json(
                            [row["source_namespace"], row["learner_id"]]
                        ),
                        "question_id": row["question_id"],
                        "skills": list(row["skills"]),
                        "partition": partition,
                        "model": name,
                        "correct": row["correct"],
                        "probability": float(value),
                        "calibrated_probability": float(calibrated_value)
                        if config.calibration
                        else None,
                    }
                )
    logistic = {
        name: value
        for name, value in summaries.items()
        if name.startswith("logistic_c") and value["eligible"]
    }
    selected_logistic = (
        min(logistic, key=lambda name: logistic[name]["validation"]["log_loss"])
        if logistic
        else None
    )
    comparisons = {}
    if "global" in predictions:
        for name, values in predictions.items():
            if name != "global":
                comparisons[name] = paired_comparison(
                    y_test,
                    values,
                    predictions["global"],
                    learners,
                    config.bootstrap_repetitions,
                    config.seed,
                )
    pq.write_table(pa.Table.from_pylist(raw_rows), path / "predictions.parquet", compression="zstd")
    return {
        "split_hash": manifest.hash,
        "audit": audit_split(
            training + validation + test,
            SplitManifest(
                {key: value for key, value in manifest.assignments.items() if value != "excluded"},
                manifest.mode,
                manifest.seed,
                manifest.parameters,
            ),
        ),
        "models": summaries,
        "population_shift": distribution_shift(training, test),
        "comparisons_to_global": comparisons,
        "selected_logistic": selected_logistic,
        "selection_rule": "Lowest validation log loss among fixed C candidates; no test metric used",
        "online_updates": config.online_updates,
        "parameter_policy": "Fit on training, freeze parameters; observed validation/test answers may update later online state",
        "bundle_policy": "Predictions within each session/timestamp unit share pre-unit state",
    }


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "# Metricon research report",
        "",
        f"Dataset: `{report['dataset_id']}`.",
        "",
        "Comparisons use identical held-out rows. Lower log loss and Brier score are better.",
        "Intervals resample whole learner histories. Associations and policy simulations are not causal evidence.",
        "",
    ]
    for index, fold in enumerate(report["folds"]):
        lines.extend(
            [
                f"## Fold {index + 1}",
                "",
                f"Split hash: `{fold['split_hash']}`.",
                "",
                "| Model | Test n | Log loss | Brier | AUROC | Calibrated log loss |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for name, model in fold["models"].items():
            if not model["eligible"]:
                lines.append(f"| {name} | unavailable | {model['reason']} | | | |")
                continue
            metric = model["test"]
            calibrated = model.get("calibrated_test", {}).get("log_loss")
            auc = metric["auroc"]
            lines.append(
                f"| {name} | {metric['n']} | {metric['log_loss']:.5f} | {metric['brier']:.5f} | {auc if auc is not None else 'unknown'} | {calibrated if calibrated is not None else 'unfitted'} |"
            )
        lines.extend(
            [
                "",
                f"Logistic selected on validation: {fold['selected_logistic']}.",
                "",
                "All eligible baselines and ablations are retained, including weaker or negative results.",
                "",
            ]
        )
    lines.extend(
        [
            f"Runtime: {report['runtime_seconds']:.2f} seconds.",
            f"Process peak RSS: {report['peak_process_rss_bytes']} bytes.",
            "",
            "See report.json for fit diagnostics, per-skill/learner slices, paired comparisons, class balance and environment.",
            "Raw predictions, exact parameters, calibration and split assignments are hashed alongside this report.",
            "",
        ]
    )
    return "\n".join(lines)
