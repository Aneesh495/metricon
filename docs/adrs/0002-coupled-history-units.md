# ADR 0002: predict and split whole coupled history units

Status: implemented.

An answer inside a bundle can reveal information about another answer in that bundle. Timestamp ties and noncontiguous session records create the same problem. Splitting individual rows or updating state between coupled targets produces an easier evaluation than the intended next-answer problem.

[History units](../../src/metricon/features/history.py) sort only within known source/learner domains. They close session intervals and overlapping timestamp ties transitively. Every target in a unit receives the state before that unit. Observed outcomes update state only after all predictions have been emitted. Legacy question-local histories remain separate domains.

[Split manifests](../../src/metricon/evaluation/splits.py) assign whole units. Training fits parameters, feature vocabulary, scaling and priors. Validation selects fixed candidates and fits calibration. The final test manifest is untouched by fitting. [Fitting scopes](../../src/metricon/features/leakage.py) record the exact authorized input identities and reject omissions, unauthorized partitions and digest changes.

The BKT fitting objective follows this prediction contract. Several same-skill answers in one unit use a composite marginal score at the shared pre-unit state. Deterministic posterior updates then apply opportunity transitions after observation. This is not an independent joint likelihood for the bundle. The policy is recorded in each report and compared with the mean-skills extension.

The tradeoff is conservative information use and sometimes smaller effective training partitions. Very large coupled units fail the documented bound; splitting them to make a task pass would violate the contract. Independent scalar BKT checks, prefix perturbations and overlapping-session tests protect this decision.
