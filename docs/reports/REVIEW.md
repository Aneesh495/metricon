# Source and scientific review

This was a separate skeptical pass over source wiring, data contracts, saved runs and failure evidence after the main implementation. It is a self-review of the project, not external peer review. [Build status](../BUILD_STATUS.md) records the final campaign outcome; raw failures remain in local evidence storage.

## Findings and remediation

| Finding | Change and evidence |
| --- | --- |
| Canonical JSON could construct an arbitrarily large object before rejection. Legacy parsing retained a growing question dictionary. | Bounded byte framing and scalar question-local parser position replaced those paths. Oversized records, malformed arrays, nested Unicode and continuation are tested in [streaming tests](../../tests/test_json_streaming.py). |
| Integer/timestamp edge cases could escape validation into storage failures. | Canonical sequences enforce signed 64-bit bounds and unsupported UTC conversions become validation errors. |
| Mixed event/bundle duration scope could omit a valid bundle in overview and session tables. | Separate eligibility/ranking preserves each event and one known bundle. The [independent boundary fixture](../../tests/test_analytics_boundaries.py) checks both totals. |
| A partial progress line could be consumed as a complete JSON record. | The coordinator advances its offset only over complete lines; the [process regression](../../tests/test_tasks.py) covers split writes. |
| Workers attempted coordinator-owned metadata writes, and equivalent splits from unrelated datasets collided in lineage. | Worker catalogs are read-only; publication and lineage registration belong to the coordinator. Split identity includes dataset identity. Actual process and cross-dataset tests cover both failures. |
| Untimed feature ordering used a memory-heavy window at the scale workload. | Spill-capable independent connections and simple independent event units avoid that unnecessary window. The failed worker log remains retained. |
| Delimiter-concatenated item/learner keys could merge distinct identifiers. | Canonical tuple keys, preserved legacy model encoding and qualified raw prediction clusters now have fitting/serialization/comparison regressions. |
| Empty or incomplete fitting-scope manifests could pass a membership-only check. | Verification requires every component, its authorized partition, complete input identities and exact hashes. Planted future dependencies, test overlap and split overlap fail. |
| Artifact verification covered payload files but did not check a changed disk manifest. | Artifact identity, catalog/disk manifest agreement, path bounds and every payload checksum are checked. Cached overview reuse verifies its artifact. |
| Experiment snapshots kept a lock checksum without the lock file. | Hashed runs now retain the actual lock, source/cache checks require it, and installed-wheel fitting/serving was exercised. |
| Scale-worker BKT timings exercised sparse fallback rather than parameter optimization. | A separate complete-history fitting campaign preserves genuine optimized parameters, diagnostics and five timing repetitions. Earlier calls remain labeled in raw records. |
| Vitest discovered the Playwright suite during locked acceptance. | Unit discovery and browser discovery use separate runners; no required browser workflow was removed. The failed command log is retained. |

The independent campaigns compare generated imports with a separate logical record map, analytical results with ordered Python histories and Polars, BKT updates with scalar equations, and fitting gradients with finite differences. Recovery injects real subprocess exits around publication, then restarts and retries. Browser tests exercise the actual API, persistent tasks and immutable outputs.

## Scientific conclusions and limits

The EdNet forward test answers a conditional prediction question for the selected eligible histories. It does not establish population representativeness or a causal benefit from a recommended action. Complete learner selection avoids random answer sampling but still defines a subset with explicit eligibility exclusions.

Validation chooses logistic regularization and calibration. Final test scores do not select hyperparameters. Learner-cluster intervals preserve observed dependence inside histories, but resampling does not remove selection bias or validate model assumptions. Post-hoc slices are diagnostics and retain their support counts.

BKT fitting and prediction follow the same coupled-unit policy. Its binary state, stationary response/transition parameters and primary-tag rule are assumptions. Composite scoring within multi-answer units is explicit. The forgetting and mean-tag extensions remain in the comparison even when they do not improve a selected reference.

Cohort IRT is identifiable only after connected support restrictions and ability constraints. Fitting succeeded on the public cohort, but its uncalibrated held-out log loss was worse than the constant baseline. Neutral predictions for unsupported items remain in the same-row evaluation. That failure is retained rather than hidden through population exclusion.

The simulator exposes latent transitions unavailable in public answers. Equal budgets, matched seeds and a misspecified process support conditional policy comparisons. They do not prove learning improvement in real students. The planner requires observed eligible duration support for timed actions and leaves missing-time actions unallocated.

Throughput is an observed property of the documented workload and host. The memory gate and throughput objective have separate results. Failed and earlier slow measurements remain useful evidence of the actual design tradeoff. The [research report](RESEARCH.md) and [performance report](PERFORMANCE.md) retain those limits alongside final measurements.
