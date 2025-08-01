# EdNet KT1 dataset card

Source: the original [Riiid EdNet repository](https://github.com/riiid/ednet), its KT1 archive and content metadata. Access and the research terms were checked during acquisition. The repository identifies the dataset as research use under CC BY-NC 4.0. Metricon source licensing does not replace these terms. Raw learner records and downloaded archives are ignored local files and are not redistributed in this repository.

[The adapter](../src/metricon/ingest/ednet.py) records source URLs, observed local SHA-256, file size, verification time and license. The source does not provide a publisher checksum here, so a local integrity checksum is not a claim of publisher authentication. An existing independently acquired archive may be adopted after ZIP integrity checking; adoption records an unknown original download date rather than inventing one.

The KT1 archive is about 1.2 GB compressed. Selection reads its ZIP directory, ranks learner files deterministically by seeded filename hash, and reads selected complete files directly. It does not extract the entire archive tree. A capped learner-file bound rejects unsupported oversized members. Selected eligible histories are retained completely rather than randomly sampling answers. The subset stops only after the required interaction and learner coverage has been reached.

Content question metadata joins question ID to the correct answer and skill tags. An observed answer equal to metadata truth yields correctness. Invalid answers, missing metadata and short unsupported sequences have explicit exclusion counts. Untagged valid questions remain accepted with empty skills. Exclusions and selected filenames are recorded in the local subset manifest. No simulator state is joined to public answers.

KT1 timestamps are shifted. Metricon preserves their source-relative order and marks them `shifted`; calendar trends are unavailable. Consecutive question records in bundles retain bundle/session identity. Repeated bundle elapsed time counts once in session totals and is never a per-question time feature. Whole bundle/session units and timestamp ties stay together in train/validation/test.

The current deterministic subset contains 200,653 accepted interactions from 1,268 learners. It excluded 172 short learner files containing 453 rows and 42 invalid answer records. There are 47 accepted untagged interactions. The canonical import had no additional rejection, duplicate or conflict. These are observations about this local subset, not claims about the full EdNet population.

| Local input | SHA-256 |
| --- | --- |
| KT1 archive | `0d13933f90201c5101c7fe8659e44474fa049e3fb93181a8ba6fb3e63267b535` |
| Content archive | `aa910a0436d9dbac0ba232f55e27b37ad8d39da285fcf15f1c1eb5d064be98e7` |
| Selected canonical NDJSON | `c88a11e359d98fb17b92d4aa9f08b3cc6d6c068d586a649213726a862d8c466c` |

```bash
make dataset-public
make experiment
```

Local provenance is under `.metricon/cache`, normalized dataset manifests under `.metricon/datasets`, and the current identifiers in `.metricon/research-state.json`. [Reproduction](REPRODUCIBILITY.md) and [research results](reports/RESEARCH.md) explain the evaluation population and limitations. If acquisition is unavailable, the adapter fixtures still test structure, but real-data validity remains unverified; synthetic observations cannot replace this card's population.
