from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import pyarrow as pa
import pyarrow.parquet as pq

from metricon.ingest.adapters import ADAPTER_VERSION, AdapterOptions, normalize, records
from metricon.quality.report import QualityReport
from metricon.schema.events import ARROW_SCHEMA, SCHEMA_VERSION, canonical_json, digest
from metricon.storage.artifacts import file_lock
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import atomic_json, file_hash, sync_directory
from metricon.storage.identities import StagedIdentityIndex, staged_entries
from metricon.storage.lineage import register_import_lineage


class ImportCancelled(RuntimeError):
    pass


def preview(path: Path, options: AdapterOptions, limit: int = 20) -> dict[str, Any]:
    if not 1 <= limit <= 1000:
        raise ValueError("Preview limit must be between 1 and 1000")
    report = QualityReport()
    examples = []
    source_hash = file_hash(path)
    for record in records(path, options):
        report.received += 1
        try:
            event = normalize(record, options, source_hash)
            report.accepted += 1
            report.observation(event)
            if len(examples) < 10:
                examples.append(event.model_dump(mode="json"))
        except (ValueError, TypeError) as error:
            report.rejected += 1
            report.problem("rejected", record.row, str(error))
        if report.received >= limit:
            break
    return {
        "source_hash": source_hash,
        "sampled": True,
        "report": report.as_dict(),
        "events": examples,
    }


def import_file(
    catalog: Catalog,
    workspace_id: str,
    path: Path,
    options: AdapterOptions,
    chunk_size: int = 8192,
    progress: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    fault: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if not 1 <= chunk_size <= 65536:
        raise ValueError("chunk_size must be between 1 and 65536")
    workspace = catalog.workspace(workspace_id)
    source_hash = file_hash(path)
    key = digest([workspace_id, source_hash, asdict(options), ADAPTER_VERSION, SCHEMA_VERSION])
    with (
        file_lock(catalog.root / "locks" / "operations.lock", shared=True),
        file_lock(catalog.root / "locks" / f"import-{workspace_id}.lock"),
    ):
        with catalog.connect() as connection:
            existing = connection.execute(
                "SELECT report FROM import_run WHERE key=?", (key,)
            ).fetchone()
        if existing:
            result = json.loads(existing["report"])
            result["duplicate_import"] = True
            return result
        workspace = catalog.workspace(workspace_id)
        parent = workspace["dataset_id"]
        stage = catalog.root / "staging" / uuid.uuid4().hex
        stage.mkdir(parents=True)
        try:
            original = stage / f"original.{options.format}"
            shutil.copyfile(path, original)
            if file_hash(original) != source_hash:
                raise ValueError("Source file changed while being copied")
            return _write_import(
                catalog,
                workspace_id,
                parent,
                stage,
                original,
                source_hash,
                key,
                options,
                chunk_size,
                progress,
                cancelled,
                fault,
            )
        finally:
            if stage.exists():
                shutil.rmtree(stage)


def _write_import(
    catalog: Catalog,
    workspace_id: str,
    parent: str | None,
    stage: Path,
    original: Path,
    source_hash: str,
    key: str,
    options: AdapterOptions,
    chunk_size: int,
    progress: Callable[[int], None] | None,
    cancelled: Callable[[], bool] | None,
    fault: Callable[[str], None] | None,
) -> dict[str, Any]:
    identities = StagedIdentityIndex(stage)
    lookup = catalog.connect()
    report = QualityReport()
    batch: list[dict[str, Any]] = []
    partitions: list[dict[str, Any]] = []
    rejection_path = stage / "quarantine.ndjson"

    def flush() -> None:
        if not batch:
            return
        name = f"part-{len(partitions):06d}.parquet"
        destination = stage / name
        table = pa.Table.from_pylist(batch, schema=ARROW_SCHEMA)
        pq.write_table(
            table, destination, compression="zstd", row_group_size=chunk_size, write_statistics=True
        )
        partitions.append({"file": name, "sha256": file_hash(destination), "rows": len(batch)})
        batch.clear()
        identities.commit()
        if progress:
            progress(report.received)
        if cancelled and cancelled():
            raise ImportCancelled("Import cancelled before publication")

    try:
        with rejection_path.open("w", encoding="utf-8") as rejected:
            for record in records(original, options):
                report.received += 1
                if report.received % chunk_size == 0 and cancelled and cancelled():
                    raise ImportCancelled("Import cancelled before publication")
                try:
                    event = normalize(record, options, source_hash)
                except (ValueError, TypeError) as error:
                    report.rejected += 1
                    rejected.write(
                        canonical_json(report.problem("rejected", record.row, str(error))) + "\n"
                    )
                    continue
                identity, content_hash = event.identity, event.content_hash
                persisted = (
                    lookup.execute(
                        "SELECT content_hash FROM event_identity WHERE workspace_id=? AND identity=?",
                        (workspace_id, identity),
                    ).fetchone()
                    if parent
                    else None
                )
                previous = persisted["content_hash"] if persisted else None
                if previous is None:
                    previous = identities.insert_or_previous(identity, content_hash)
                if previous is not None:
                    if previous == content_hash:
                        report.duplicates += 1
                    else:
                        report.conflicts += 1
                        rejected.write(
                            canonical_json(
                                report.problem(
                                    "conflict",
                                    record.row,
                                    "Stable identity has different content",
                                    identity,
                                )
                            )
                            + "\n"
                        )
                    continue
                batch.append(event.arrow_row(identity, content_hash))
                report.accepted += 1
                report.observation(event)
                if len(batch) >= chunk_size:
                    flush()
            flush()
            rejected.flush()
            os.fsync(rejected.fileno())
        identities.commit()
    finally:
        identities.close()
        lookup.close()
    if fault:
        fault("after_partitions")
    base = catalog.dataset(parent)["manifest"] if parent else {"partitions": [], "row_count": 0}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "adapter_options": asdict(options),
        "parent": parent,
        "source": {"sha256": source_hash, "format": options.format, "namespace": options.namespace},
        "import_key": key,
        "row_count": base["row_count"] + report.accepted,
        "new_partitions": partitions,
        "quality": report.as_dict(),
        "identity_index": identities.manifest(),
    }
    identifier = digest(manifest) if report.accepted else parent
    result = {
        "import_key": key,
        "dataset_id": identifier,
        "source_hash": source_hash,
        "duplicate_import": False,
        "report": report.as_dict(),
    }
    destination = catalog.root / "datasets" / (identifier if report.accepted else f"empty-{key}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest["partitions"] = base["partitions"] + [
        {**entry, "path": str((destination / entry["file"]).relative_to(catalog.root))}
        for entry in partitions
    ]
    atomic_json(stage / "manifest.json", manifest)
    for item in stage.iterdir():
        if item.is_file():
            with item.open("rb") as handle:
                os.fsync(handle.fileno())
    if fault:
        fault("before_rename")
    if destination.exists():
        raise RuntimeError("Unexpected existing dataset publication directory")
    os.rename(stage, destination)
    sync_directory(destination.parent)
    if fault:
        fault("after_rename")
    publication = {
        "operation": "import",
        "workspace_id": workspace_id,
        "parent": parent,
        "destination": str(destination.relative_to(catalog.root)),
        "identifier": identifier,
        "accepted": report.accepted,
        "manifest": manifest,
        "key": key,
        "result": result,
        "source_hash": source_hash,
    }
    if catalog.read_only:
        catalog.deferred_publications.append(publication)
    else:
        commit_import(catalog, publication, fault)
    return result


def commit_import(
    catalog: Catalog, publication: dict[str, Any], fault: Callable[[str], None] | None = None
) -> None:
    workspace_id, parent = publication["workspace_id"], publication["parent"]
    identifier, key = publication["identifier"], publication["key"]
    manifest, result = publication["manifest"], publication["result"]
    source_hash = publication["source_hash"]
    destination = (catalog.root / publication["destination"]).resolve()
    if not destination.is_relative_to(catalog.root / "datasets"):
        raise ValueError("Import publication is outside the dataset store")
    if not (destination / "manifest.json").is_file():
        raise ValueError("Import publication has no manifest")
    if json.loads((destination / "manifest.json").read_text()) != manifest:
        raise ValueError("Import publication manifest changed")
    if file_hash(destination / f"original.{manifest['source']['format']}") != source_hash:
        raise ValueError("Original source checksum changed before publication")
    if sum(part["rows"] for part in manifest["new_partitions"]) != publication["accepted"]:
        raise ValueError("Published partition counts disagree with accepted rows")
    for partition in manifest["new_partitions"]:
        if file_hash(destination / partition["file"]) != partition["sha256"]:
            raise ValueError("Import publication checksum changed")
    try:
        with catalog.transaction() as connection:
            current = connection.execute(
                "SELECT dataset_id FROM workspace WHERE id=?", (workspace_id,)
            ).fetchone()[0]
            if current != parent:
                raise RuntimeError("Workspace dataset changed during import")
            if publication["accepted"]:
                connection.executemany(
                    "INSERT INTO event_identity VALUES (?,?,?)",
                    (
                        (workspace_id, identity, content_hash)
                        for identity, content_hash in staged_entries(destination, manifest)
                    ),
                )
                connection.execute(
                    "INSERT INTO dataset VALUES (?,?,?,?,?,?)",
                    (
                        identifier,
                        workspace_id,
                        parent,
                        canonical_json(manifest),
                        manifest["row_count"],
                        time.time(),
                    ),
                )
                connection.execute(
                    "UPDATE workspace SET dataset_id=? WHERE id=?", (identifier, workspace_id)
                )
                catalog.add_lineage(
                    connection,
                    identifier,
                    {"source": source_hash, **({"previous": parent} if parent else {})},
                )
                register_import_lineage(catalog, connection, publication)
            connection.execute(
                "INSERT INTO import_run VALUES (?,?,?,?,?)",
                (key, workspace_id, identifier, canonical_json(result), time.time()),
            )
            if fault:
                fault("before_commit")
    except BaseException:
        shutil.rmtree(destination)
        raise


def reconcile(catalog: Catalog) -> dict[str, Any]:
    removed = []
    with (
        file_lock(catalog.root / "locks" / "coordinator.lock", blocking=False),
        file_lock(catalog.root / "locks" / "operations.lock", blocking=False),
    ):
        with catalog.connect() as connection:
            committed = {row[0] for row in connection.execute("SELECT id FROM dataset")}
            imports = {row[0] for row in connection.execute("SELECT key FROM import_run")}
            artifacts = {row[0] for row in connection.execute("SELECT id FROM artifact")}
        for directory in (catalog.root / "staging").glob("*"):
            if directory.is_dir():
                shutil.rmtree(directory)
                removed.append(str(directory.relative_to(catalog.root)))
        for directory in (catalog.root / "datasets").glob("*"):
            empty_committed = directory.name.startswith("empty-") and directory.name[6:] in imports
            if directory.is_dir() and directory.name not in committed and not empty_committed:
                shutil.rmtree(directory)
                removed.append(str(directory.relative_to(catalog.root)))
        for directory in (catalog.root / "artifacts").glob("*"):
            if directory.is_dir() and directory.name not in artifacts:
                shutil.rmtree(directory)
                removed.append(str(directory.relative_to(catalog.root)))
    return {"removed": removed}
