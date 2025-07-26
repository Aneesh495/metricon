from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from metricon.schema.events import canonical_json, digest


def file_hash(path: Path, chunk_bytes: int = 1024 * 1024) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_bytes), b""):
            result.update(chunk)
    return result.hexdigest()


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(canonical_json(value))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    sync_directory(path.parent)


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def hash_tree(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): file_hash(item)
        for item in sorted(path.rglob("*"))
        if item.is_file() and item.name != "artifact.json"
    }


def artifact_identity(path: Path, metadata: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    manifest = {"files": hash_tree(path), "metadata": metadata, "artifact_version": "artifact/1"}
    return digest(manifest), manifest
