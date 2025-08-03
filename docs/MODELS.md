# Models, derivations and interpretation

All predictors implement fit, pre-answer predict, optional online state update, parameters, save and load. Serialized `models/1` payloads retain fitted parameters and state, and history models retain the feature contract. An experiment fits on training rows, serializes its warm training state, predicts validation, then predicts test with frozen parameters. State updates follow the recorded evaluation option. Model state and observed answer performance have different meanings.

## Predictive baselines

[GlobalBaseline](../src/metricon/models/baselines.py) uses a Beta(1,1) smoothed global proportion. ItemPrior shrinks training-only item successes/counts toward that global rate. Unknown items fall back to the global rate. Item keys use canonical JSON tuples of source namespace and item ID; delimiter characters cannot merge distinct items. Saved older colon-encoded models retain their recorded encoding on load, and new fitting uses tuple encoding. RecentHistory uses a bounded learner recent-answer buffer, updated only after a coupled unit. Baselines are always reported even when they beat other models.

LogisticHistory maps pre-unit history dictionaries to a sparse training vocabulary, then applies training-only maximum-absolute scaling and L2 regularized logistic fitting. Features include prior learner/item rates and counts, recent history, supplied skills/kind, missingness and within-domain gaps. The fixed candidates are C = 0.1, 1 and 10. Validation log loss selects the candidate; test scores do not select it. Unknown categories have no fitted coefficient. Coefficients describe associations on this training population and scale, not causal effects or certified knowledge.

## Bayesian knowledge tracing

Let K be the prior probability of knowing a skill, L the learning probability, S slip, G guess, and F optional forgetting. The pre-answer probability is

`p = K(1-S) + (1-K)G`.

Conditioning on a correct answer gives `posterior = K(1-S)/p`. Conditioning on an incorrect answer gives `posterior = KS/[KS + (1-K)(1-G)]`. The next opportunity prior is

`K_next = posterior(1-F) + (1-posterior)L`.

The order matters: predict, condition on the observed outcome, then transition. Forgetting is per opportunity, not elapsed real time. It is a separately evaluated extension; missing timestamps never become a forgetting clock. Logarithms and divisions use bounded probabilities for numerical stability.

[BKT](../src/metricon/models/bkt.py) fits initial knowledge, learning, slip and guess per supplied skill using bounded multi-start L-BFGS-B and an analytic forward derivative. Initial knowledge is bounded to [0.001,0.999], learning to [0.0001,0.6], slip/guess to [0.001,0.4]; forgetting, when enabled, has its own bound. The seed and all start diagnostics are retained. Sparse skills with fewer than 30 observations or two histories use explicit defaults and are marked unfitted. Convergence and boundary diagnostics must be read alongside predictions.

All predictions in a coupled unit share the state before that unit. Once predictions are emitted, observations are conditioned in deterministic source order with one opportunity transition per observed skill. Fitting scores the same pre-unit marginal probabilities. With several same-skill answers in a unit, the objective is a composite marginal log score, not a claim that their labels are independent likelihood factors. With one skill observation per unit, it is the standard sequential BKT likelihood. Independent scalar equations, long all-correct/all-incorrect histories, and finite-difference gradients test the implementation.

The default multi-skill policy assigns the first sorted skill. The evaluated mean-skills ablation fits each tagged skill and averages their pre-answer probabilities, updating each tagged state afterward. This is an explicit heuristic for annotation ambiguity, not a joint latent conjunction model. Untagged items use an explicit fallback. State is keyed to known order domains so legacy question histories do not invent a cross-question chronology. A high posterior is a conditional model estimate. The workbench retrospective replay uses saved fitted parameters; it is labeled separately from held-out prediction evidence.

## Hierarchical observed performance

[HierarchicalBetaBinomial](../src/metricon/models/hierarchical.py) models item successes `s_i | p_i ~ Binomial(n_i,p_i)` and `p_i ~ Beta(alpha,beta)`. Bounded regularized empirical Bayes fitting estimates shared alpha/beta from training item counts. The posterior for item i is `Beta(alpha+s_i,beta+n_i-s_i)`. Sparse counts shrink toward the pooled mean; quantiles express observed-performance uncertainty.

The without-shrinkage ablation uses separate Beta(1,1) priors. Neither estimator measures latent knowledge or separates learner ability from item selection. Empirical Bayes intervals condition on fitted hyperparameters; they omit their estimation uncertainty. This limitation matters on sparse and heterogeneous datasets.

## Cohort item response

[IRT](../src/metricon/models/irt.py) uses `p_ui = sigmoid(a_i(theta_u-b_i))`. One-parameter IRT fixes discrimination to one and centers ability. Two-parameter IRT centers/scales ability to unit variance and bounds discrimination to [0.25,3]. Difficulty is bounded to [-6,6]. The regularized objective is binary cross entropy plus ability/difficulty penalties and, for 2PL, a log-discrimination penalty. Analytic gradients are checked through an independent finite-difference optimizer wrapper.

Eligibility requires at least 20 supported learners, at least 10 responses per learner and 20 responses per item by default, both outcome classes, and sufficient connected item support. Iterative response-count pruning keeps the largest connected learner/item graph; discarded rows are reported. One person's sparse records cannot produce population difficulty. Frozen item parameters support online ability updates, but unseen items return an explicit neutral probability. Reports retain cold-item support and same-row overall scores so sparse exclusions cannot improve an apparent comparison by dropping difficult targets.

Item diagnostics include response counts, conditional information-based uncertainty, fitted boundaries and cohort pruning. Conditional standard errors omit joint parameter covariance and are approximate. Two-parameter optimization can be unstable even after identification constraints; a fitted model is not automatically a useful predictor. Cohort difficulty and ability are relative to its eligible population, not universal measures.

## Calibration and comparison

Platt calibration fits a sigmoid of validation log odds. It requires at least 30 validation observations and both classes; otherwise it remains an explicit unfitted identity mapping. Both calibrated and uncalibrated test scores are reported. Ten fixed equal-width probability bins define ECE. Bin uncertainty and denominator labels accompany charts.

Log loss, Brier, accuracy and eligible AUROC share frozen target rows. Whole learner-cluster bootstrap uses source-qualified learner tuples and resamples histories, retaining all events from each drawn learner. Paired comparisons use the same cluster draws for both models. Seeds and repetition counts permit exact repetition. Forward evaluation gives warm learners; learner-held-out evaluation tests new-learner generalization. These answer different questions.

Source: [feature state](../src/metricon/features/history.py), [fit scopes](../src/metricon/features/leakage.py), [splits](../src/metricon/evaluation/splits.py), [calibration](../src/metricon/evaluation/calibration.py), [metrics](../src/metricon/evaluation/metrics.py), [frozen verification](../src/metricon/evaluation/frozen.py). Read [model cards](MODEL_CARDS.md) before using predictions.
