import argparse
from pathlib import Path

from metricon.evaluation.campaigns import (
    generated_analytics,
    generated_ingestion,
    interruption_campaign,
)

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, default=Path(".metricon"))
arguments = parser.parse_args()
root = arguments.root / "verification"
for path, run in [
    (root / "ingestion/ingestion.json", lambda: generated_ingestion(root / "ingestion")),
    (root / "analytics/analytics.json", lambda: generated_analytics(root / "analytics")),
    (root / "recovery/recovery.json", lambda: interruption_campaign(root / "recovery")),
]:
    run()
