# ADR 0004: use exact disk identities and independent analytical connections

Status: implemented and measured.

Idempotence cannot rely on a probabilistic filter alone. A false positive would discard a valid practice attempt, while a changed payload under an existing event ID must become a conflict. Keeping every identity in a Python dictionary also prevents large-file streaming.

[Staged identity indexes](../../src/metricon/storage/identities.py) route full SHA-256 identity/content digests into 64 SQLite shards using digest prefix bits. Digests remain complete; the routing prefix is not a truncated identity. Shard caches have explicit limits. The uncommitted staging indexes use disposable journaling settings and close before publication. The coordinator merges exact identities into the transactional catalog only at publication.

Staging failure can lose the staging index without losing committed data. [Import publication](../../src/metricon/ingest/pipeline.py) validates original and partition hashes, records normalization options and atomically advances the catalog pointer. Recovery removes unregistered outputs under ownership locks. Originals and immutable Parquet remain the source of reconstruction.

[Analytical connections](../../src/metricon/storage/query.py) scan immutable partitions with two DuckDB threads, a memory limit and a unique spill directory per connection. There is no shared writable DuckDB cache. Untimed uncoupled feature scans avoid a window that previously exhausted the analytical memory limit at scale.

The shard approach improves the observed large-file import over the earlier random text-key tree but retains an exact coordinator merge and original-file copy cost. The [performance report](../reports/PERFORMANCE.md) preserves raw repetitions and the unmet throughput target. The measured RSS bound applies to its documented workload and profile; arbitrary event sizes have their own parser and batch bounds.
