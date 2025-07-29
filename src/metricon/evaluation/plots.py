from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from metricon.analytics.statistics import beta_summary
from metricon.features.history import domain, units
from metricon.storage.artifacts import ArtifactWriter, verify_artifact
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json
from metricon.storage.query import scan_events


def scientific_plots(catalog: Catalog, run: str, benchmark_path: Path | None = None) -> str:
    os.environ.setdefault("MPLCONFIGDIR", str(catalog.root / "matplotlib-cache"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import duckdb

    artifact = catalog.artifact(run)
    if artifact["kind"] != "experiment" or not verify_artifact(catalog, run)["valid"]:
        raise ValueError("Scientific plots require a verified fitted experiment")
    dataset = artifact["dataset_id"]
    report = json.loads((catalog.root / "artifacts" / run / "report.json").read_text())
    fold = report["folds"][0]
    choices = [
        name
        for name in ["global", "bkt", fold.get("selected_logistic")]
        if name and fold["models"].get(name, {}).get("eligible")
    ]
    plt.rcParams.update(
        {"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 140}
    )
    figures: dict[str, Any] = {}
    with ArtifactWriter(catalog, "scientific-plots", dataset) as writer:
        figure, axis = plt.subplots(figsize=(6.5, 5))
        axis.plot([0, 1], [0, 1], "--", color="gray", label="Perfect calibration")
        calibration_raw = {}
        for name in choices:
            bins = [
                item for item in fold["models"][name]["test"]["calibration"]["bins"] if item["n"]
            ]
            x = [item["prediction"] for item in bins]
            y = np.array([item["observed"]["estimate"] for item in bins])
            low = np.array([item["observed"]["lower"] for item in bins])
            high = np.array([item["observed"]["upper"] for item in bins])
            axis.errorbar(x, y, yerr=[y - low, high - y], marker="o", capsize=3, label=name)
            calibration_raw[name] = bins
        axis.set(
            xlabel="Mean held-out predicted probability",
            ylabel="Observed correct proportion with Wilson interval",
            xlim=(0, 1),
            ylim=(0, 1),
            title="Frozen test predictions: equal-width calibration bins",
        )
        axis.legend()
        figure.tight_layout()
        figure.savefig(writer.path / "calibration.png")
        figure.savefig(writer.path / "calibration.svg")
        plt.close(figure)
        figures["calibration"] = calibration_raw

        models = [
            (name, value["test"]["log_loss"])
            for name, value in fold["models"].items()
            if value["eligible"]
        ]
        names, losses = zip(*models)
        figure, axis = plt.subplots(figsize=(8, max(4, len(names) * 0.3)))
        axis.barh(
            names,
            losses,
            color=[
                "#b68035"
                if "without" in name or "forgetting" in name or "mean_skills" in name
                else "#3a6c81"
                for name in names
            ],
        )
        axis.set(
            xlabel="Mean test log loss, lower is better",
            title="Baselines and ablations retained on identical targets",
        )
        axis.invert_yaxis()
        figure.tight_layout()
        figure.savefig(writer.path / "ablations.png")
        plt.close(figure)
        figures["ablations"] = [{"model": name, "log_loss": value} for name, value in models]

        rows = scan_events(catalog, dataset).collect().to_dicts()
        histories: dict[Any, int] = {}
        index_lookup = {}
        counts = {}
        for unit in units(rows):
            for row in unit:
                index_lookup[row["identity"]] = histories.get(domain(row), 0)
                aggregate = counts.setdefault(row["question_id"], [0, 0])
                aggregate[0] += int(row["correct"])
                aggregate[1] += 1
            for row in unit:
                key = domain(row)
                histories[key] = histories.get(key, 0) + 1
        question_rows = sorted(counts.items(), key=lambda pair: (pair[1][1], pair[0]))[:20]
        posteriors = [
            {"question": question, **beta_summary(successes, n)}
            for question, (successes, n) in question_rows
        ]
        figure, axis = plt.subplots(figsize=(7, 5))
        means = np.array([row["mean"] for row in posteriors])
        lower = np.array([row["lower"] for row in posteriors])
        upper = np.array([row["upper"] for row in posteriors])
        axis.errorbar(
            means, np.arange(len(means)), xerr=[means - lower, upper - means], fmt="o", capsize=3
        )
        axis.set_yticks(
            np.arange(len(means)), [f"{row['question']} (n={row['n']})" for row in posteriors]
        )
        axis.set(
            xlabel="Observed performance posterior, Beta(1+s, 1+n-s)",
            xlim=(0, 1),
            title="Sparse-item uncertainty, not latent knowledge",
        )
        figure.tight_layout()
        figure.savefig(writer.path / "uncertainty.png")
        plt.close(figure)
        figures["uncertainty"] = posteriors

        path = catalog.root / "artifacts" / run / "fold-0/predictions.parquet"
        with duckdb.connect(":memory:") as connection:
            prediction_rows = connection.execute(
                "SELECT identity,model,correct,probability FROM read_parquet(?) WHERE partition='test'",
                [str(path)],
            ).fetchall()
        learning = {}
        for identity, name, correct, probability in prediction_rows:
            if name not in choices:
                continue
            bucket = index_lookup[identity] // 25
            entry = learning.setdefault((name, bucket), [0, 0.0, 0])
            entry[0] += 1
            entry[1] += -np.log(probability if correct else 1 - probability)
            entry[2] += int(correct)
        learning_rows = [
            {
                "model": name,
                "past_event_start": bucket * 25,
                "past_event_end": bucket * 25 + 24,
                "n": value[0],
                "log_loss": value[1] / value[0],
                "correct": value[2],
            }
            for (name, bucket), value in sorted(learning.items())
        ]
        figure, axis = plt.subplots(figsize=(7, 4.5))
        for name in choices:
            series = [row for row in learning_rows if row["model"] == name and row["n"] >= 30]
            axis.plot(
                [row["past_event_start"] for row in series],
                [row["log_loss"] for row in series],
                marker="o",
                label=name,
            )
        axis.set(
            xlabel="Observed past events before target unit, bins of 25",
            ylabel="Mean held-out log loss",
            title="Prediction error across history length, n >= 30 per bin",
        )
        axis.legend()
        figure.tight_layout()
        figure.savefig(writer.path / "learning-curve.png")
        plt.close(figure)
        figures["learning-curve"] = learning_rows

        if benchmark_path and benchmark_path.is_file():
            benchmark = json.loads(benchmark_path.read_text())
            sizes = sorted({row["rows"] for row in benchmark["repetitions"]})
            rates = [
                [row["rows_per_second"] for row in benchmark["repetitions"] if row["rows"] == size]
                for size in sizes
            ]
            figure, axes = plt.subplots(1, 2, figsize=(9, 4))
            axes[0].plot(sizes, [np.median(values) for values in rates], marker="o")
            axes[0].set(
                xscale="log",
                xlabel="Input records",
                ylabel="Measured records per second",
                title="Five-repetition import medians",
            )
            rss = [
                max(
                    row["peak_import_rss_bytes"]
                    for row in benchmark["repetitions"]
                    if row["rows"] == size
                )
                / (1024**3)
                for size in sizes
            ]
            axes[1].plot(sizes, rss, marker="o")
            axes[1].axhline(2, linestyle="--", color="gray", label="Import RSS limit")
            axes[1].set(
                xscale="log",
                xlabel="Input records",
                ylabel="Maximum observed peak import RSS, GiB",
                title="Fresh worker process measurements",
            )
            axes[1].legend()
            figure.tight_layout()
            figure.savefig(writer.path / "scale.png")
            plt.close(figure)
            figures["scale"] = benchmark["summaries"]
        atomic_json(
            writer.path / "figure-data.json",
            {
                "run": run,
                "dataset_id": dataset,
                "figures": figures,
                "learning_curve_limit": "History-length associations can reflect changing population and item mix; not causal learning effects",
            },
        )
        return writer.publish(
            {"run": run, "figures": list(figures), "dataset_id": dataset}, parents={"run": run}
        )
