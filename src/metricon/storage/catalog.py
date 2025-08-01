from __future__ import annotations

import contextlib
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

from metricon.schema.events import canonical_json

DDL = """
CREATE TABLE IF NOT EXISTS workspace (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('user','synthetic','research')),
 dataset_id TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS dataset (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspace(id), parent_id TEXT,
 manifest TEXT NOT NULL, row_count INTEGER NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS import_run (
 key TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, dataset_id TEXT,
 report TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS event_identity (
 workspace_id TEXT NOT NULL, identity TEXT NOT NULL, content_hash TEXT NOT NULL,
 PRIMARY KEY (workspace_id, identity)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS artifact (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, dataset_id TEXT NOT NULL,
 manifest TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS lineage (
 child TEXT NOT NULL, parent TEXT NOT NULL, role TEXT NOT NULL,
 PRIMARY KEY(child, parent, role)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS lineage_node (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, metadata TEXT NOT NULL,
 locator TEXT, checksum TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS job (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, dataset_id TEXT NOT NULL,
 kind TEXT NOT NULL, parameters TEXT NOT NULL, status TEXT NOT NULL,
 progress REAL NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '', result_id TEXT,
 error TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
 created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS job_status ON job(status, created_at);
CREATE INDEX IF NOT EXISTS dataset_workspace ON dataset(workspace_id, created_at);
CREATE INDEX IF NOT EXISTS artifact_dataset ON artifact(dataset_id, kind);
"""


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *arguments: Any) -> None:
        try:
            super().__exit__(*arguments)
        finally:
            self.close()


class Catalog:
    def __init__(self, root: Path, read_only: bool = False):
        self.root = root.resolve()
        self.read_only = read_only
        self.deferred_publications: list[dict[str, Any]] = []
        if not read_only:
            self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "catalog.sqlite"
        if not read_only:
            with self.connect() as connection:
                connection.executescript(DDL)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{self.path}?mode=ro" if self.read_only else str(self.path),
            uri=self.read_only,
            timeout=30,
            isolation_level=None,
            factory=ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        if not self.read_only:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if self.read_only:
            raise RuntimeError("Workers cannot mutate coordinator metadata")
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def create_workspace(self, name: str, kind: str = "user") -> dict[str, Any]:
        identifier = uuid.uuid4().hex
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO workspace VALUES (?, ?, ?, NULL, ?)",
                (identifier, name, kind, time.time()),
            )
        return self.workspace(identifier)

    def workspace(self, identifier: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM workspace WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError("Workspace does not exist")
        return dict(row)

    def workspaces(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute("SELECT * FROM workspace ORDER BY created_at")
            ]

    def dataset(self, identifier: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM dataset WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError("Dataset does not exist")
        import json

        result = dict(row)
        result["manifest"] = json.loads(result["manifest"])
        return result

    def datasets(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, parent_id, row_count, created_at FROM dataset WHERE workspace_id=? ORDER BY created_at DESC",
                (workspace_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def artifact(self, identifier: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM artifact WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError("Artifact does not exist")
        import json

        result = dict(row)
        result["manifest"] = json.loads(result["manifest"])
        return result

    def artifacts(self, dataset_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT id, kind, created_at FROM artifact WHERE dataset_id=?"
        arguments: list[Any] = [dataset_id]
        if kind is not None:
            sql += " AND kind=?"
            arguments.append(kind)
        with self.connect() as connection:
            rows = connection.execute(sql + " ORDER BY created_at DESC", arguments).fetchall()
        return [dict(row) for row in rows]

    def ancestors(self, identifier: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                WITH RECURSIVE parents(child,parent,role) AS (
                  SELECT child,parent,role FROM lineage WHERE child=?
                  UNION SELECT l.child,l.parent,l.role FROM lineage l JOIN parents p ON l.child=p.parent
                ) SELECT DISTINCT * FROM parents
            """,
                (identifier,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_lineage(
        self, connection: sqlite3.Connection, child: str, parents: dict[str, str]
    ) -> None:
        for role, parent in parents.items():
            if child == parent:
                raise ValueError("A lineage node cannot depend on itself")
            connection.execute(
                "INSERT OR IGNORE INTO lineage VALUES (?,?,?)", (child, parent, role)
            )

    def record_artifact(
        self,
        identifier: str,
        kind: str,
        dataset_id: str,
        manifest: dict[str, Any],
        parents: dict[str, str],
    ) -> None:
        if self.read_only:
            self.deferred_publications.append(
                {
                    "operation": "artifact",
                    "identifier": identifier,
                    "kind": kind,
                    "dataset_id": dataset_id,
                    "manifest": manifest,
                    "parents": parents,
                }
            )
            return
        with self.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO artifact VALUES (?,?,?,?,?)",
                (identifier, kind, dataset_id, canonical_json(manifest), time.time()),
            )
            self.add_lineage(connection, identifier, {"dataset": dataset_id, **parents})
