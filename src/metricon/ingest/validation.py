from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from metricon.ingest.adapters import AdapterOptions
from metricon.ingest.pipeline import import_file
from metricon.storage.catalog import Catalog


def validate_file(path: Path, options: AdapterOptions) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="metricon-validation-") as directory:
        catalog = Catalog(Path(directory))
        workspace = catalog.create_workspace("Validation only", "user")
        result = import_file(catalog, workspace["id"], path, options)
    return {
        "valid": result["report"]["rejected"] == 0 and result["report"]["conflicts"] == 0,
        "source_hash": result["source_hash"],
        "report": result["report"],
        "scope": "Full-file schema, duplicate, and conflict validation in a temporary store; no workspace pointer changes",
    }
