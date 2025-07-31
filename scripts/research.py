import argparse
import json
from pathlib import Path

from metricon.evaluation.experiment import ExperimentConfig, run_experiment
from metricon.evaluation.research import public_dataset
from metricon.ingest.demo import demo_workspace
from metricon.storage.catalog import Catalog

parser = argparse.ArgumentParser()
parser.add_argument("action", choices=["dataset", "experiment"])
parser.add_argument("--root", type=Path, default=Path(".metricon"))
arguments = parser.parse_args()
catalog = Catalog(arguments.root)
if arguments.action == "dataset":
    result = public_dataset(catalog)
else:
    state = catalog.root / "research-state.json"
    if state.exists():
        dataset = json.loads(state.read_text())["dataset_id"]
    else:
        dataset = demo_workspace(catalog)["workspace"]["dataset_id"]
    run = run_experiment(
        catalog, dataset, ExperimentConfig(), progress=lambda _, message: print(message, flush=True)
    )
    result = {"dataset_id": dataset, "artifact_id": run}
print(json.dumps(result, indent=2))
