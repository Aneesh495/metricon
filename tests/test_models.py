import numpy as np
import pytest
from scipy.optimize import approx_fprime

from conftest import event
from metricon.features.history import HistoryFeatures
from metricon.models.base import load_model, save_model
from metricon.models.baselines import GlobalBaseline, ItemPrior, RecentHistory, LogisticHistory
from metricon.models.bkt import BKT, BKTParameters, forward_objective, padded_sequences, step
from metricon.models.hierarchical import HierarchicalBetaBinomial
from metricon.models.irt import IRT, IRTEligibilityError


def scalar_reference(outcomes, initial, learning, slip, guess, forgetting):
    k = initial
    results = []
    for correct in outcomes:
        p = k * (1 - slip) + (1 - k) * guess
        if correct:
            posterior = (k * (1 - slip)) / p
        else:
            posterior = (k * slip) / (k * slip + (1 - k) * (1 - guess))
        k = posterior * (1 - forgetting) + (1 - posterior) * learning
        results.append((p, posterior, k))
    return results


@pytest.mark.parametrize("outcomes", [[True, False, True], [True] * 1000, [False] * 1000, []])
def test_bkt_independent_scalar_equations(outcomes):
    parameters = BKTParameters(0.21, 0.11, 0.13, 0.19, 0.02)
    reference = scalar_reference(outcomes, 0.21, 0.11, 0.13, 0.19, 0.02)
    k = parameters.initial
    for outcome, expected in zip(outcomes, reference):
        result = step(k, outcome, parameters)
        np.testing.assert_allclose(result, expected, rtol=1e-12)
        k = result[2]


def test_bkt_gradient_independent_finite_difference():
    matrices = padded_sequences([[1, 0, 1, 1], [0, 0, 1], [1] * 5])
    parameters = np.array([0.2, 0.1, 0.1, 0.2, 0.02])
    _, gradient = forward_objective(parameters, matrices, True)
    numerical = approx_fprime(parameters, lambda p: forward_objective(p, matrices, True)[0], 1e-7)
    np.testing.assert_allclose(gradient, numerical, rtol=2e-5, atol=2e-5)


def test_bundle_features_do_not_see_coupled_answers():
    rows = [
        event(0, session_id="same").arrow_row(),
        event(1, session_id="same").arrow_row(),
        event(2, session_id="next").arrow_row(),
    ]
    features, _ = HistoryFeatures().transform(rows)
    assert features[0]["learner_log_attempts"] == features[1]["learner_log_attempts"] == 0
    assert features[2]["learner_log_attempts"] == np.log1p(2)
    mutated = [dict(row) for row in rows]
    mutated[1]["correct"] = False
    changed, _ = HistoryFeatures().transform(mutated)
    assert features[0] == changed[0] and features[1] == changed[1]


def test_bkt_coupled_objective_matches_independent_scalar_reference():
    from metricon.models.bkt import forward_objective

    parameters = np.array([0.2, 0.1, 0.08, 0.22])
    observations = np.array([[1], [0], [1], [1]], dtype=np.int8)
    starts = np.array([[1], [0], [1], [0]], dtype=np.int8)
    knowledge = float(parameters[0])
    loss = 0.0
    held = knowledge
    for outcome, marker in zip(observations[:, 0], starts[:, 0]):
        if marker:
            held = knowledge
        predicted = held * (1 - parameters[2]) + (1 - held) * parameters[3]
        loss -= np.log(predicted if outcome else 1 - predicted)
        instantaneous = knowledge * (1 - parameters[2]) + (1 - knowledge) * parameters[3]
        likelihood = 1 - parameters[2] if outcome else parameters[2]
        posterior = knowledge * likelihood / (instantaneous if outcome else 1 - instantaneous)
        knowledge = posterior + (1 - posterior) * parameters[1]
    actual, gradient = forward_objective(parameters, [observations], False, [starts])
    assert actual == pytest.approx(loss, abs=1e-12)
    for index in range(4):
        above, below = parameters.copy(), parameters.copy()
        above[index] += 1e-6
        below[index] -= 1e-6
        numeric = (
            forward_objective(above, [observations], False, [starts])[0]
            - forward_objective(below, [observations], False, [starts])[0]
        ) / 2e-6
        assert gradient[index] == pytest.approx(numeric, abs=1e-5)


@pytest.mark.parametrize(
    "factory",
    [
        GlobalBaseline,
        ItemPrior,
        RecentHistory,
        LogisticHistory,
        HierarchicalBetaBinomial,
        lambda: BKT(starts=1, max_iterations=10),
        lambda: IRT(1, minimum_item_responses=5),
    ],
)
def test_model_serialization(factory, rows, tmp_path):
    model = factory().fit(rows)
    path = tmp_path / "model.json"
    save_model(path, model)
    restored = load_model(path)
    future = [event(99, learner="future", question="q1").arrow_row()]
    np.testing.assert_allclose(
        model.predict(future, False), restored.predict(future, False), rtol=1e-12
    )


def test_irt_rejects_personal_history(rows):
    with pytest.raises(IRTEligibilityError):
        IRT().fit([row for row in rows if row["learner_id"] == "u0"])


def test_irt_2pl_identifiability(rows):
    model = IRT(2, minimum_item_responses=5, max_iterations=50).fit(rows)
    ability = np.array(list(model.abilities.values()))
    assert abs(ability.mean()) < 1e-8
    assert abs(ability.std() - 1) < 1e-5
    assert all(0.25 <= item["discrimination"] <= 3.000001 for item in model.items.values())


def test_logistic_warm_serialized_state(rows, tmp_path):
    model = LogisticHistory().fit(rows)
    path = tmp_path / "warm.json"
    save_model(path, model)
    restored = load_model(path)
    future = [event(99, learner="u0", question="q1").arrow_row()]
    np.testing.assert_allclose(
        model.predict(future, False), restored.predict(future, False), rtol=1e-12
    )


def test_overlapping_sessions_merge_without_future_leakage():
    from metricon.features.history import units

    rows = [
        event(0, session_id="a").arrow_row(),
        event(1, session_id="b").arrow_row(),
        event(2, session_id="a").arrow_row(),
    ]
    assert len(list(units(rows))) == 1
    features, _ = HistoryFeatures().transform(rows)
    assert all(value["learner_log_attempts"] == 0 for value in features)
