from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from metricon.schema.events import digest
from metricon.storage.hashing import atomic_json, file_hash

EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    ".metricon",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".cache",
    "work",
    "docs",
}
SOURCE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".css",
    ".html",
    ".svg",
    ".toml",
    ".yaml",
    ".yml",
}


def source_manifest(repository: Path) -> dict[str, Any]:
    files = {}
    for path in sorted(repository.rglob("*")):
        relative = path.relative_to(repository)
        if any(part in EXCLUDED_DIRECTORIES for part in relative.parts) or not path.is_file():
            continue
        if path.suffix in SOURCE_SUFFIXES or relative.as_posix() in {
            "package.json",
            "web/package.json",
            "package-lock.json",
            "uv.lock",
            "Makefile",
            ".python-version",
        }:
            files[relative.as_posix()] = file_hash(path)
    return {
        "method": "SHA-256 of actual authored source, tests, configuration and dependency locks including uncommitted contents; runtime outputs excluded",
        "files": files,
        "hash": digest(files),
        "exclusions": sorted(EXCLUDED_DIRECTORIES),
    }


def record_command(
    repository: Path, destination: Path, name: str, command: list[str]
) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    for suffix in [".log", ".json"]:
        previous = destination / f"{name}{suffix}"
        if previous.exists():
            archive = destination / "previous"
            archive.mkdir(exist_ok=True)
            previous.rename(archive / f"{name}-{time.time_ns()}{suffix}")
    started = time.perf_counter()
    process = subprocess.run(
        command, cwd=repository, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    path = destination / f"{name}.log"
    path.write_text(process.stdout)
    result = {
        "command": command,
        "exit_code": process.returncode,
        "runtime_seconds": time.perf_counter() - started,
        "log": str(path),
        "sha256": file_hash(path),
    }
    atomic_json(destination / f"{name}.json", result)
    if process.returncode:
        raise RuntimeError(f"Required command failed: {name}; raw log retained at {path}")
    return result


def private_census(repository: Path, destination: Path) -> dict[str, Any]:
    process = subprocess.run(
        [sys.executable, str(repository / "scripts/count_production.py")],
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(process.stdout)
    atomic_json(destination, result)
    return result


def evidence_manifest(paths: list[Path], base: Path) -> dict[str, Any]:
    entries = {}
    for path in paths:
        if not path.is_file():
            raise ValueError(f"Required evidence is missing: {path}")
        entries[str(path.relative_to(base))] = {
            "sha256": file_hash(path),
            "bytes": path.stat().st_size,
        }
    return {"files": entries, "hash": digest(entries)}


def verify_files(base: Path, manifest: dict[str, Any]) -> list[str]:
    errors = []
    if digest(manifest["files"]) != manifest["hash"]:
        errors.append("Evidence manifest digest mismatch")
    for name, expected in manifest["files"].items():
        path = (base / name).resolve()
        if (
            not path.is_relative_to(base.resolve())
            or not path.is_file()
            or file_hash(path) != expected["sha256"]
        ):
            errors.append(f"Missing or changed evidence: {name}")
    return errors
