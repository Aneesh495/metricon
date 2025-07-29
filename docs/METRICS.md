# Metric glossary

| Metric | Eligible denominator and meaning |
| --- | --- |
| All-attempt accuracy | All accepted events; repeated attempts remain distinct when their identities differ. |
| First-attempt accuracy | Earliest answer for each source, learner, and question using available timestamp, source sequence, and identity. |
| Streak | Consecutive correct answers within one known order domain. Separate question-local legacy histories never become a global streak. |
| Retries before first success | Position of the first correct answer in a question history. Never-solved histories are censored and reported separately. |
| Duration | Finite known event duration, or one known bundle duration per explicit session/bundle. Unknown time remains unknown. |
| Session behavior | Explicit session IDs, answer counts, unique items and bundles, observed accuracy, and deduplicated known duration. |
| Proportion uncertainty | Two-sided 95% Wilson intervals. Empty groups have null estimates. Small samples are marked. |
| Observed-performance posterior | Beta-Binomial uncertainty over answer performance. It is not a measurement of latent knowledge. |
| Cohort percentile | Midrank against actual eligible peers with sufficient attempts and shared item support. Item frequencies and learner selection can still differ. |
| Log loss | Mean negative log probability assigned to the observed binary outcome. Predictions are clipped only for numerical safety. |
| Brier score | Mean squared probability error. |
| AUROC | Pairwise discrimination over both observed classes. A single-class population is ineligible. |
| Calibration error | Count-weighted absolute observed-minus-predicted difference over ten fixed equal-width probability bins. Empty bins remain unknown. |

Every API aggregate identifies its dataset version. Skill-tag denominators overlap when an item has multiple tags. Time charts include only real timestamps; shifted EdNet timestamps support relative ordering, not calendar behavior. Downsampling retains counts and binary extrema.

Drift compares two actual adjacent learner windows with adequate support. Response, missingness, and item coverage warnings do not refit a model. Response intervals currently assume independent observations within windows, so repeated answer dependence remains a limitation. Experiment uncertainty uses whole learner clusters instead.
