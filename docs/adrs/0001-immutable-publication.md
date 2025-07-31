# ADR 0001: Immutable files and coordinator publication

Status: accepted.

Canonical observations must survive import interruption without exposing half a dataset. SQLite stores metadata and identity ownership; versioned Parquet stores normalized observations. A worker writes a unique staging directory, hashes and synchronizes its files, renames the directory, and submits a publication request. The coordinator verifies files and changes the workspace pointer in one SQLite transaction. Workers open catalog metadata read-only.

An unregistered renamed directory is an orphan. Startup reconciliation holds exclusive coordinator and operation locks before deleting orphans. A registered directory is retained. Import cancellation before publication preserves the prior pointer; artifact cancellation publishes no result. Recovery tests terminate real child processes at publication boundaries, then reconcile and retry.

Identity staging uses 64 disk B-trees keyed by complete binary SHA-256 digests. Each cache is bounded at 16 MiB. A fixed digest prefix routes records without truncating identity. Exact duplicates and changed-content conflicts still compare the full content hash. Sorted shard traversal populates the durable catalog in its owning transaction. Staging disables its own journal because these files have no committed durability role before directory publication. The catalog keeps WAL and FULL synchronization.

This costs an additional local copy of imported originals and an exact identity index. It avoids an unbounded Python identity dictionary and a shared writable analytical database. Per-query DuckDB connections independently scan committed Parquet, with a memory limit and spill directory.

Source: [publication](../../src/metricon/ingest/pipeline.py), [identity index](../../src/metricon/storage/identities.py), [process coordinator](../../src/metricon/tasks/coordinator.py), [recovery campaign](../../src/metricon/evaluation/campaigns.py).
