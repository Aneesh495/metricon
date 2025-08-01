# Canonical events and streaming adapters

The schema is `attempt/1`. [AttemptEvent](../src/metricon/schema/events.py) is the authoritative validator and Arrow contract. A normalized row is an immutable observation, not an assessment of knowledge.

| Field | Contract |
| --- | --- |
| `source_namespace`, `event_id` | Nonempty NFC-normalized strings, at most 512 characters, no control characters. Together define stable identity. |
| `learner_id`, `question_id` | Explicit identifiers or supplied local pseudonyms. Preserve source meaning; do not infer demographic attributes. |
| `skills` | Sorted unique string tags. Missing tags become an empty array, not an invented skill. |
| `correct` | A JSON boolean. Strings, integers, null and truthy objects are rejected. |
| `attempt_kind` | `practice`, `assessment`, `review`, or `unknown`. |
| `source_sequence` | A nonnegative integer. It orders records only within the declared source domain. |
| `timestamp` | Nullable timezone-aware ISO-8601 timestamp, normalized to UTC. Numeric epoch values are not canonical timestamps. |
| `time_semantics` | `real`, `shifted`, or `unknown`. Missing timestamps require `unknown`. |
| `duration_ms` | Nullable finite nonnegative number. Zero is a known value. |
| `duration_scope` | `event`, `bundle`, or `unknown`. Missing duration requires `unknown`. |
| `session_id`, `bundle_id` | Nullable explicit identifiers. Bundle duration requires these for elapsed-time aggregation. |
| `order_scope` | `learner` or `question`. Legacy browser exports are question-local. |
| `provenance` | Source checksum, adapter, input row, original ID, identity quality and explanatory note. |

Identity is SHA-256 of canonical JSON `[source_namespace, event_id]`. Content hash is SHA-256 of the normalized event excluding provenance. Import identity includes workspace, original-file checksum, adapter options, schema and adapter versions. An identical file retry returns its previous import report. An identical event in another file is a duplicate. A changed answer or other normalized content under the same event identity is a conflict. A genuinely repeated answer with a different stable event ID remains a distinct observation.

```json
{"source_namespace":"practice","event_id":"answer-19","learner_id":"local","question_id":"q1","skills":["algebra"],"correct":false,"attempt_kind":"practice","source_sequence":19,"timestamp":"2026-01-01T10:00:00-05:00","time_semantics":"real","duration_ms":45000,"duration_scope":"event","session_id":"session-2","bundle_id":null}
```

Adapters replace incoming provenance with observed file provenance. Unknown canonical fields fail validation. Inconsistencies fail rather than being silently repaired. Preview validates a bounded prefix and labels its report sampled. `metricon validate` scans the complete file in an isolated temporary store, including identity checks, and returns a failing exit code for invalid data.

## Format behavior

[Adapters](../src/metricon/ingest/adapters.py) separate parsing from normalization.

| Format | Streaming and edge cases |
| --- | --- |
| Legacy question-keyed JSON | `ijson` parses nested question objects and attempt arrays. Explicit attempt IDs are preserved; missing IDs use documented position-only identity. There is no timestamp, duration or global chronology inference. |
| Canonical JSON array | Bounded byte framing keeps strings and nested records within the configured item bound. Oversized events produce a quarantine record. Invalid structural JSON terminates the import without publication. |
| NDJSON | Binary bounded line reader. Malformed JSON, invalid UTF-8 and oversized lines are rejected independently; later lines remain eligible. |
| CSV | Standard quoted-field parser, UTF-8 with optional BOM, strict unique header. Correctness is exactly `true` or `false`; skills are a JSON array in a quoted cell. Structural CSV errors terminate the file. |
| Parquet | Arrow row batches, independent canonical validation. Incoming identity/hash fields are recalculated. |
| EdNet KT1 | Answer metadata joins and complete source sequences, described in the [dataset card](PUBLIC_DATA.md). |

CSV exports prefix spreadsheet-active literal strings and mark `csv_encoding=spreadsheet-literal-v1`. Import removes that protection only when the marker is present. IDs containing a genuine apostrophe are otherwise unchanged. JSON, NDJSON, CSV and Parquet round trips retain normalized event identity/content.

Missing legacy attempt IDs cannot distinguish an inserted earlier record from an existing position after export edits. The report marks this identity limitation. Use stable source IDs for longitudinal imports. Source namespaces and learner pseudonyms are explicit import choices; do not use a different namespace merely to evade conflict detection.

## Quality and publication

[QualityReport](../src/metricon/quality/report.py) maintains accepted, duplicate, conflict and rejected counts, missingness, known-order coverage and bounded diagnostic samples. Full rejection records stream into `quarantine.ndjson`; raw malformed content is not copied into a browser page. Reports preserve input row references. The API paginates inspection.

Parquet is compressed with Zstandard, fixed Arrow fields and row-group statistics. A manifest names all inherited and new partitions, source and normalization versions, hashes, counts and identity shards. Source copies, manifest and partitions are synchronized before directory rename. Coordinator publication verifies originals and output files, then commits the exact identity index, dataset registration, lineage and workspace pointer together. See [ownership](ARCHITECTURE.md) and [recovery](TASKS.md).

Ordering is deterministic within `(source, learner, question-local domain)`: available UTC timestamp, source sequence, event ID. Timestamp ties and entire sessions are indivisible prediction/split units. Overlapping session spans close transitively. Event ID breaks display ties; it does not establish a real time interval. Unknown-time records remain explicitly unknown.

Source specifications: [canonical fields](../src/metricon/schema/events.py), [parser behavior](../src/metricon/ingest/adapters.py), [import transaction](../src/metricon/ingest/pipeline.py), [exact staged index](../src/metricon/storage/identities.py), [audit](../src/metricon/quality/audit.py).
