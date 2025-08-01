# Model cards

These local models predict binary practice outcomes and explain observed histories. They do not grade students, certify mastery or identify a causal study effect. Dataset/run IDs, population support, calibration and fit diagnostics accompany each use.

| Family | Intended use | Main constraints and failure modes |
| --- | --- | --- |
| Global constant | Reproducible no-history reference | Learner/item mixtures can make one rate inappropriate. Training class balance determines it. |
| Item prior | Stable item-level predictive reference | Exposure and learner selection confound observed item performance. Unknown items use the global rate. |
| Recent history | Short observed-history reference | Choice of recent buffer is fixed; response dependence and changing item mix can dominate. |
| Logistic history | Interpretable associations and prediction | Vocabulary and scaling are training-only. Correlated features limit coefficient interpretation. Convergence warnings remain visible. |
| Hierarchical Beta-Binomial | Sparse observed-performance uncertainty | Exchangeable item prior can be misspecified. Hyperparameter uncertainty is not integrated. No latent-knowledge claim. |
| BKT | Inspectable skill-state dynamics | Supplied tags, binary latent state, stationary slip/guess/learning and opportunity transitions are assumptions. Sparse defaults are not fitted evidence. |
| BKT forgetting | Evaluate an additional transition mechanism | Per-opportunity forgetting is not an elapsed-time memory model. Retain negative held-out outcomes. |
| 1PL cohort IRT | Relative cohort learner/item structure | Connected graph/count restrictions and ability centering are necessary. Poor held-out performance invalidates predictive usefulness. |
| 2PL cohort IRT | Explore bounded discrimination differences | Identification, sparse support, boundary effects and optimization instability matter. Conditional item uncertainty is approximate. |

Personal imports can fit eligible baseline, history and sparse-performance components. Cohort IRT is unavailable without actual supported population data. A recommendation using BKT links to the saved run, observed history, uncertainty and factor contributions. It remains a study-planning heuristic.

Training and evaluation use whole sessions and timestamp ties. Evaluation answers can update later online states only when the run explicitly enables that behavior; model parameters remain frozen. Unknown global chronology in browser exports is never repaired by fake dates. Raw learner IDs should be pseudonyms; this local application provides no remote multi-user authentication or tenant isolation.

The [research report](reports/RESEARCH.md) publishes every eligible baseline and ablation, including failures. Reproduce the run before treating a plotted model as current. A different input, adapter, split, feature contract or fitted artifact identifies a different result.
