from __future__ import annotations

import contextlib
import fcntl
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Iterator

from metricon.storage.catalog import Catalog
from metricon.storage.hashing import artifact_identity, atomic_json, file_hash, sync_directory


@contextlib.contextmanager
def file_lock(path: Path, blocking: bool = True, shared: bool = False) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        fcntl.flock(
            handle,
            (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | (0 if blocking else fcntl.LOCK_NB),
        )
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class ArtifactWriter:
    def __init__(self, catalog: Catalog, kind: str, dataset_id: str):
        self.catalog = catalog
        self.kind = kind
        self.dataset_id = dataset_id
        self.path = catalog.root / "staging" / uuid.uuid4().hex
        self.operation_lock: Any = None
        self.published = False

    def __enter__(self) -> ArtifactWriter:
        self.operation_lock = file_lock(
            self.catalog.root / "locks" / "operations.lock", shared=True
        )
        self.operation_lock.__enter__()
        self.path.mkdir(parents=True)
        return self

    def publish(self, metadata: dict[str, Any], parents: dict[str, str] | None = None) -> str:
        identifier, manifest = artifact_identity(self.path, {"kind": self.kind, **metadata})
        atomic_json(self.path / "artifact.json", manifest)
        for file in self.path.rglob("*"):
            if file.is_file():
                with file.open("rb") as handle:
                    os.fsync(handle.fileno())
        destination = self.catalog.root / "artifacts" / identifier
        destination.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(self.catalog.root / "locks" / "publish.lock"):
            if destination.exists():
                shutil.rmtree(self.path)
            else:
                os.rename(self.path, destination)
                sync_directory(destination.parent)
            self.catalog.record_artifact(
                identifier, self.kind, self.dataset_id, manifest, parents or {}
            )
        self.published = True
        return identifier

    def __exit__(self, *arguments: Any) -> None:
        try:
            if self.path.exists():
                shutil.rmtree(self.path)
        finally:
            if self.operation_lock:
                self.operation_lock.__exit__(*arguments)


def verify_artifact(catalog: Catalog, identifier: str) -> dict[str, Any]:
    manifest = catalog.artifact(identifier)["manifest"]
    directory = catalog.root / "artifacts" / identifier
    errors = []
    for name, expected in manifest["files"].items():
        path = directory / name
        if not path.is_file() or file_hash(path) != expected:
            errors.append(name)
    return {"id": identifier, "valid": not errors, "invalid_files": errors}
