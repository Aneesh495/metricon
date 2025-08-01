from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from metricon.schema.events import canonical_json, digest
from metricon.storage.catalog import Catalog
from metricon.storage.hashing import file_hash

NODE_DDL = """
CREATE TABLE IF NOT EXISTS lineage_node (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, metadata TEXT NOT NULL,
 locator TEXT, checksum TEXT, created_at REAL NOT NULL
);
"""


class LineageGraph:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        if not catalog.read_only:
            with catalog.connect() as connection:
                connection.executescript(NODE_DDL)

    def register(
        self,
        identifier: str,
        kind: str,
        metadata: dict[str, Any],
        parents: dict[str, str] | None = None,
        locator: Path | None = None,
        checksum: str | None = None,
    ) -> str:
        if not identifier or not kind:
            raise ValueError("Lineage nodes require an identifier and a kind")
        relative = str(locator.relative_to(self.catalog.root)) if locator else None
        with self.catalog.transaction() as connection:
            previous = connection.execute(
                "SELECT * FROM lineage_node WHERE id=?", (identifier,)
            ).fetchone()
            if previous is not None:
                if previous["kind"] != kind or json.loads(previous["metadata"]) != metadata:
                    raise ValueError("Content-addressed lineage node has conflicting metadata")
            else:
                connection.execute(
                    "INSERT INTO lineage_node VALUES (?,?,?,?,?,?)",
                    (identifier, kind, canonical_json(metadata), relative, checksum, time.time()),
                )
            for role, parent in (parents or {}).items():
                self._assert_acyclic(connection, identifier, parent)
                connection.execute(
                    "INSERT OR IGNORE INTO lineage VALUES (?,?,?)", (identifier, parent, role)
                )
        return identifier

    @staticmethod
    def _assert_acyclic(connection: sqlite3.Connection, child: str, parent: str) -> None:
        if child == parent:
            raise ValueError("Lineage self-dependency is invalid")
        reaches_child = connection.execute(
            """
          WITH RECURSIVE ancestry(id) AS (
            SELECT ? UNION SELECT l.parent FROM lineage l JOIN ancestry a ON l.child=a.id
          ) SELECT 1 FROM ancestry WHERE id=? LIMIT 1
        """,
            (parent, child),
        ).fetchone()
        if reaches_child:
            raise ValueError("Lineage edge creates a cycle")

    def graph(self, identifier: str) -> dict[str, Any]:
        edges = self.catalog.ancestors(identifier)
        identifiers = sorted(
            {identifier, *[edge["child"] for edge in edges], *[edge["parent"] for edge in edges]}
        )
        nodes = []
        with self.catalog.connect() as connection:
            for node_id in identifiers:
                row = connection.execute(
                    "SELECT * FROM lineage_node WHERE id=?", (node_id,)
                ).fetchone()
                if row is not None:
                    node = dict(row)
                    node["metadata"] = json.loads(node["metadata"])
                    nodes.append(node)
                    continue
                dataset = connection.execute(
                    "SELECT id,manifest FROM dataset WHERE id=?", (node_id,)
                ).fetchone()
                artifact = connection.execute(
                    "SELECT id,kind,manifest FROM artifact WHERE id=?", (node_id,)
                ).fetchone()
                kind = (
                    "dataset"
                    if dataset
                    else artifact["kind"]
                    if artifact
                    else "source-or-legacy-node"
                )
                nodes.append(
                    {"id": node_id, "kind": kind, "metadata": {}, "locator": None, "checksum": None}
                )
        levels = self.topological_levels(nodes, edges)
        return {
            "root": identifier,
            "nodes": nodes,
            "edges": edges,
            "levels": levels,
            "acyclic": True,
            "meaning": "All parent content identities must remain identical to reproduce a descendant.",
        }

    @staticmethod
    def topological_levels(
        nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> list[list[str]]:
        parents = {node["id"]: set() for node in nodes}
        for edge in edges:
            parents[edge["child"]].add(edge["parent"])
        completed: set[str] = set()
        remaining = set(parents)
        levels = []
        while remaining:
            ready = sorted(node for node in remaining if parents[node].issubset(completed))
            if not ready:
                raise ValueError("Committed lineage contains a cycle")
            levels.append(ready)
            completed.update(ready)
            remaining.difference_update(ready)
        return levels

    def descendants(self, identifier: str) -> list[str]:
        with self.catalog.connect() as connection:
            rows = connection.execute(
                """
                WITH RECURSIVE children(id) AS (
                  SELECT child FROM lineage WHERE parent=?
                  UNION SELECT l.child FROM lineage l JOIN children c ON l.parent=c.id
                ) SELECT id FROM children ORDER BY id
            """,
                (identifier,),
            ).fetchall()
        return [row["id"] for row in rows]

    def verify(self, identifier: str) -> dict[str, Any]:
        graph = self.graph(identifier)
        inspected = []
        unavailable = []
        invalid = []
        for node in graph["nodes"]:
            locator = node.get("locator")
            checksum = node.get("checksum")
            if not locator or not checksum:
                unavailable.append(node["id"])
                continue
            path = self.catalog.root / locator
            if not path.is_file() or file_hash(path) != checksum:
                invalid.append(node["id"])
            else:
                inspected.append(node["id"])
        return {
            "root": identifier,
            "verified_nodes": inspected,
            "invalid_nodes": invalid,
            "metadata_only_nodes": unavailable,
            "valid": not invalid,
            "scope": "Available immutable files; metadata-only source references are not file verification.",
        }


def source_code_hash(root: Path) -> dict[str, Any]:
    files = {
        path.relative_to(root).as_posix(): file_hash(path) for path in sorted(root.rglob("*.py"))
    }
    return {
        "hash": digest(files),
        "files": files,
        "method": "SHA-256 of reusable Python source files",
    }


def register_import_lineage(
    catalog: Catalog, connection: sqlite3.Connection, publication: dict[str, Any]
) -> None:
    manifest = publication["manifest"]
    identifier = publication["identifier"]
    directory = catalog.root / publication["destination"]

    def node(node_id: str, kind: str, metadata: dict, path: Path | None = None) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO lineage_node VALUES (?,?,?,?,?,?)",
            (
                node_id,
                kind,
                canonical_json(metadata),
                str(path.relative_to(catalog.root)) if path else None,
                file_hash(path) if path else None,
                time.time(),
            ),
        )

    source_hash = publication["source_hash"]
    node(
        source_hash,
        "original-source",
        {"sha256": source_hash},
        directory / f"original.{manifest['source']['format']}",
    )
    transform = {
        "schema_version": manifest["schema_version"],
        "adapter_version": manifest["adapter_version"],
        "options": manifest.get("adapter_options", manifest["source"]),
    }
    transform_id = digest(transform)
    node(transform_id, "normalization-contract", transform)
    node(
        identifier,
        "dataset",
        {"row_count": manifest["row_count"], "schema_version": manifest["schema_version"]},
        directory / "manifest.json",
    )
    connection.execute(
        "INSERT OR IGNORE INTO lineage VALUES (?,?,?)", (identifier, transform_id, "normalization")
    )
    for partition in manifest["partitions"]:
        partition_id = digest(["canonical-parquet", partition["sha256"]])
        node(
            partition_id,
            "canonical-partition",
            {"sha256": partition["sha256"], "rows": partition["rows"]},
            catalog.root / partition["path"],
        )
        connection.execute(
            "INSERT OR IGNORE INTO lineage VALUES (?,?,?)", (identifier, partition_id, "partition")
        )


def register_experiment_lineage(catalog: Catalog, artifact_id: str) -> dict[str, Any]:
    artifact = catalog.artifact(artifact_id)
    if artifact["kind"] != "experiment":
        raise ValueError("Experiment lineage requires an experiment artifact")
    dataset_id = artifact["dataset_id"]
    while dataset_id:
        dataset = catalog.dataset(dataset_id)
        with catalog.transaction() as connection:
            register_import_lineage(
                catalog,
                connection,
                {
                    "manifest": dataset["manifest"],
                    "identifier": dataset_id,
                    "destination": f"datasets/{dataset_id}",
                    "source_hash": dataset["manifest"]["source"]["sha256"],
                },
            )
        dataset_id = dataset["parent_id"]
    graph = LineageGraph(catalog)
    root = catalog.root / "artifacts" / artifact_id
    files = artifact["manifest"]["files"]
    file_nodes = {}
    for name in sorted(files):
        if name.endswith("split.json"):
            split = json.loads((root / name).read_text())
            split_hash = digest(split)
            node_id = digest([artifact["dataset_id"], split_hash])
            graph.register(
                node_id,
                "split-manifest",
                {"dataset_id": artifact["dataset_id"], "split_hash": split_hash},
                {"dataset": artifact["dataset_id"]},
            )
    for name, checksum in sorted(files.items()):
        if name.startswith("source/") or name == "source-manifest.json":
            kind = "pipeline-source"
        elif name == "feature-contract.json":
            kind = "feature-contract"
        elif name == "environment.json":
            kind = "locked-environment"
        elif name.endswith("split.json"):
            kind = "split"
        elif name.endswith(".model.json"):
            kind = "fitted-model"
        elif name.endswith(".calibration.json"):
            kind = "validation-calibration"
        elif name.endswith("predictions.parquet"):
            kind = "held-out-predictions"
        elif name.endswith("report.json"):
            kind = "evaluation-report"
        else:
            kind = "report-view"
        node_id = digest([artifact_id, name, checksum])
        graph.register(
            node_id,
            kind,
            {"file": name, "sha256": checksum},
            locator=root / name,
            checksum=checksum,
        )
        file_nodes[name] = node_id
    for name, node_id in file_nodes.items():
        fold_directory = str(Path(name).parent)
        parents = {"dataset": artifact["dataset_id"]}
        if name.endswith(".model.json"):
            parents["feature-contract"] = (
                file_nodes["feature-contract.json"]
                if "feature-contract.json" in file_nodes
                else artifact["dataset_id"]
            )
            if "source-manifest.json" in file_nodes:
                parents["source"] = file_nodes["source-manifest.json"]
            if "environment.json" in file_nodes:
                parents["environment"] = file_nodes["environment.json"]
        split_name = fold_directory + "/split.json"
        if split_name in file_nodes and split_name != name:
            parents["split"] = file_nodes[split_name]
        model_name = name.replace(".calibration.json", ".model.json")
        if name.endswith(".calibration.json") and model_name in file_nodes:
            parents["model"] = file_nodes[model_name]
        if name.endswith("predictions.parquet"):
            for file, identifier in file_nodes.items():
                if str(Path(file).parent) == fold_directory and file.endswith(
                    (".model.json", ".calibration.json")
                ):
                    parents[file] = identifier
        if name == "report.json":
            for file, identifier in file_nodes.items():
                if file.endswith("predictions.parquet"):
                    parents[file] = identifier
        with catalog.transaction() as connection:
            for role, parent in parents.items():
                graph._assert_acyclic(connection, node_id, parent)
                connection.execute(
                    "INSERT OR IGNORE INTO lineage VALUES (?,?,?)", (node_id, parent, role)
                )

    with catalog.transaction() as connection:
        for name, identifier in file_nodes.items():
            connection.execute(
                "INSERT OR IGNORE INTO lineage VALUES (?,?,?)", (artifact_id, identifier, name)
            )
    return graph.graph(artifact_id)
