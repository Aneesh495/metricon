from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

from metricon.storage.hashing import file_hash


class StagedIdentityIndex:
    """Exact disk-backed identities with a fixed aggregate page-cache ceiling.

    The first six digest bits route full SHA-256 keys to one of 64 B-trees.
    No digest is truncated. Binary keys halve payload relative to hexadecimal
    text; each small tree gets at most 16 MiB of cache. The staging files have
    no durability role before their containing dataset is published.
    """

    SHARDS = 64
    CACHE_KIB = 16384

    def __init__(self, directory: Path):
        self.directory = directory
        self.connections: dict[int, sqlite3.Connection] = {}
        self.count = 0

    def _connection(self, number: int) -> sqlite3.Connection:
        if number not in self.connections:
            connection = sqlite3.connect(self.directory / f"identity-{number:02x}.sqlite")
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute(f"PRAGMA cache_size=-{self.CACHE_KIB}")
            connection.execute(
                "CREATE TABLE identity (id BLOB PRIMARY KEY, hash BLOB NOT NULL) WITHOUT ROWID"
            )
            self.connections[number] = connection
        return self.connections[number]

    def insert_or_previous(self, identity: str, content_hash: str) -> str | None:
        key, value = bytes.fromhex(identity), bytes.fromhex(content_hash)
        if len(key) != 32 or len(value) != 32:
            raise ValueError("Identity index requires complete SHA-256 digests")
        connection = self._connection(key[0] >> 2)
        inserted = connection.execute(
            "INSERT OR IGNORE INTO identity VALUES (?,?)", (key, value)
        ).rowcount
        if inserted:
            self.count += 1
            return None
        return (
            connection.execute("SELECT hash FROM identity WHERE id=?", (key,)).fetchone()[0].hex()
        )

    def commit(self) -> None:
        for connection in self.connections.values():
            connection.commit()

    def close(self) -> None:
        for connection in self.connections.values():
            connection.close()

    def manifest(self) -> dict:
        return {
            "version": "binary-shards/1",
            "rows": self.count,
            "shards": [
                {"file": path.name, "sha256": file_hash(path)}
                for path in sorted(self.directory.glob("identity-*.sqlite"))
            ],
            "maximum_cache_bytes": self.SHARDS * self.CACHE_KIB * 1024,
        }


def staged_entries(directory: Path, manifest: dict) -> Iterator[tuple[str, str]]:
    """Iterate full keys in global order, without attaching many databases.

    Ordered insertion also bounds catalog B-tree churn inside the one owning
    publication transaction. Compatibility with original text-key staging
    permits recovery of already prepared publications.
    """
    index = manifest.get("identity_index")
    if index is None:
        paths = [directory / "identities.sqlite"]
    else:
        if index["version"] != "binary-shards/1":
            raise ValueError("Unknown staged identity index version")
        paths = []
        for entry in index["shards"]:
            path = (directory / entry["file"]).resolve()
            if path.parent != directory.resolve() or file_hash(path) != entry["sha256"]:
                raise ValueError("Staged identity index checksum changed")
            paths.append(path)
    for path in paths:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            for key, value in connection.execute("SELECT id,hash FROM identity ORDER BY id"):
                yield (key.hex(), value.hex()) if isinstance(key, bytes) else (key, value)
        finally:
            connection.close()
