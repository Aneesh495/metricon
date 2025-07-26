from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import ijson
import pyarrow.parquet as pq

from metricon.schema.events import AttemptEvent, Provenance, digest

ADAPTER_VERSION = "adapters/1"


@dataclass(frozen=True)
class RawRecord:
    row: int
    value: dict[str, Any] | None
    error: str | None = None


@dataclass(frozen=True)
class AdapterOptions:
    format: str
    namespace: str = "local"
    learner: str = "local-learner"
    max_line_bytes: int = 4 * 1024 * 1024
    max_event_bytes: int = 4 * 1024 * 1024


def strict_csv_boolean(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError("CSV correctness accepts exactly true or false")


def csv_value(row: dict[str, str | None]) -> dict[str, Any]:
    if None in row:
        raise ValueError("CSV has more fields than its header")
    result: dict[str, Any] = dict(row)
    result["correct"] = strict_csv_boolean(str(result.get("correct")))
    result["source_sequence"] = int(result.get("source_sequence", ""))
    result["skills"] = json.loads(result.get("skills") or "[]")
    for key in ["timestamp", "session_id", "bundle_id"]:
        if not result.get(key):
            result[key] = None
    duration = result.get("duration_ms")
    result["duration_ms"] = None if duration in (None, "") else float(duration)
    for key in [
        "schema_version",
        "attempt_kind",
        "order_scope",
        "time_semantics",
        "duration_scope",
    ]:
        if result.get(key) in ("", None):
            result.pop(key, None)
    result.pop("provenance", None)
    return result


def iter_ndjson(path: Path, options: AdapterOptions) -> Iterator[RawRecord]:
    with path.open("rb") as handle:
        index = 0
        while True:
            line = handle.readline(options.max_line_bytes + 1)
            if not line:
                break
            index += 1
            if len(line) > options.max_line_bytes:
                while line and not line.endswith(b"\n"):
                    line = handle.readline(options.max_line_bytes + 1)
                yield RawRecord(index, None, "Line exceeds configured byte bound")
                continue
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("Event must be a JSON object")
                yield RawRecord(index, value)
            except (UnicodeDecodeError, ValueError) as error:
                yield RawRecord(index, None, str(error))


def iter_csv(path: Path, options: AdapterOptions) -> Iterator[RawRecord]:
    csv.field_size_limit(options.max_event_bytes)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV header is missing or has duplicate columns")
        for index, row in enumerate(reader, 1):
            try:
                yield RawRecord(index, csv_value(row))
            except (ValueError, TypeError) as error:
                yield RawRecord(index, None, str(error))


def iter_parquet(path: Path, options: AdapterOptions) -> Iterator[RawRecord]:
    parquet = pq.ParquetFile(path)
    index = 0
    for batch in parquet.iter_batches(batch_size=4096):
        for row in batch.to_pylist():
            index += 1
            for key in ["identity", "content_hash", "provenance"]:
                row.pop(key, None)
            yield RawRecord(index, row)


def iter_json(path: Path, options: AdapterOptions) -> Iterator[RawRecord]:
    with path.open("rb") as handle:
        for index, value in enumerate(ijson.items(handle, "item", use_float=True), 1):
            if isinstance(value, dict):
                yield RawRecord(index, value)
            else:
                yield RawRecord(index, None, "Canonical JSON must contain an array of objects")


def iter_legacy(path: Path, options: AdapterOptions) -> Iterator[RawRecord]:
    builder: ijson.ObjectBuilder | None = None
    prefix_in_progress: str | None = None
    question: str | None = None
    sequences: dict[str, int] = {}
    index = 0
    size = 0
    with path.open("rb") as handle:
        for prefix, kind, value in ijson.parse(handle, use_float=True):
            if builder is None and kind == "map_key":
                if prefix == "" and value != "LocalSubmissions":
                    question = str(value)
                elif prefix == "LocalSubmissions":
                    question = str(value)
            if builder is None and kind == "start_map" and prefix.endswith(".attempts.item"):
                builder = ijson.ObjectBuilder()
                prefix_in_progress = prefix
                size = 0
            if builder is not None:
                size += len(str(value)) + len(prefix) + 16
                if size > options.max_event_bytes:
                    raise ValueError("Legacy attempt exceeds configured byte bound")
                builder.event(kind, value)
                if prefix == prefix_in_progress and kind == "end_map":
                    index += 1
                    attempt = builder.value
                    if question is None:
                        raise ValueError("Legacy attempt lacks question key")
                    sequence = sequences.get(question, 0)
                    sequences[question] = sequence + 1
                    identifier = attempt.get("id")
                    quality = (
                        "stable"
                        if isinstance(identifier, str) and identifier.strip()
                        else "position_only"
                    )
                    if quality == "position_only":
                        identifier = f"position:{sequence}"
                    yield RawRecord(
                        index,
                        {
                            "source_namespace": options.namespace,
                            "event_id": digest([options.learner, question, identifier]),
                            "learner_id": options.learner,
                            "question_id": question,
                            "correct": attempt.get("correct"),
                            "skills": [],
                            "source_sequence": sequence,
                            "attempt_kind": "unknown",
                            "timestamp": None,
                            "duration_ms": None,
                            "order_scope": "question",
                            "_original_id": str(identifier),
                            "_identity_quality": quality,
                        },
                    )
                    builder = None
                    prefix_in_progress = None
    if builder is not None:
        raise ValueError("Incomplete legacy attempt")


ADAPTERS = {
    "legacy": iter_legacy,
    "csv": iter_csv,
    "ndjson": iter_ndjson,
    "parquet": iter_parquet,
    "json": iter_json,
}


def records(path: Path, options: AdapterOptions) -> Iterator[RawRecord]:
    if options.format not in ADAPTERS:
        raise ValueError(f"Unsupported format {options.format}")
    yield from ADAPTERS[options.format](path, options)


def normalize(record: RawRecord, options: AdapterOptions, source_hash: str) -> AttemptEvent:
    if record.error is not None or record.value is None:
        raise ValueError(record.error or "Missing record")
    value = dict(record.value)
    original_id = value.pop("_original_id", value.get("event_id"))
    quality = value.pop("_identity_quality", "stable")
    value.pop("provenance", None)
    value.setdefault("source_namespace", options.namespace)
    value.setdefault("learner_id", options.learner)
    if value["source_namespace"] != options.namespace:
        raise ValueError("Event namespace differs from selected import namespace")
    value["provenance"] = Provenance(
        source_hash=source_hash,
        adapter=f"{options.format}:{ADAPTER_VERSION}",
        row=record.row,
        original_id=original_id,
        identity_quality=quality,
    )
    return AttemptEvent.model_validate(value)
