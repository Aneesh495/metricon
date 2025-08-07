# ADR 0003: retain frozen predictions and unsuccessful models

Status: implemented.

A displayed metric must identify its population, split, model and probability stream. Recomputing predictions after changing parameters makes historical comparisons ambiguous. Removing an unfavorable baseline can make an elaborate model appear useful without evidence.

[Experiments](../../src/metricon/evaluation/experiment.py) publish raw validation and test predictions, fitted parameters, calibration, fitting scopes, environment and source snapshots in one hashed artifact. Calibration uses validation only. Parameters remain frozen while the recorded option permits observed evaluation answers to update later online state. The serialized warm training state remains available independently of evaluation updates.

[Frozen evaluation](../../src/metricon/evaluation/frozen.py) recomputes metrics from saved probability files. [Comparison](../../src/metricon/evaluation/comparison.py) pairs only identical dataset/split/target populations and preserves source-qualified learner clusters. Different populations receive descriptive comparisons. Cluster intervals preserve histories; the bootstrap seed and repetition count are part of the result.

Every eligible baseline and ablation remains in reports, including weaker calibrated models and cohort IRT results. Predictive quality targets and throughput targets have separate outcomes from system correctness. A fitted model, green build or screenshot cannot establish research validity.

This consumes local artifact storage and preserves more results than a dashboard usually displays. It makes later analysis traceable and prevents a changed dependency from quietly replacing an older conclusion. Raw public learner records remain local under their source terms; committed reports contain aggregate results and reproducible commands.
