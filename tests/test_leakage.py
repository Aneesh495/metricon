import pytest

from metricon.evaluation.splits import forward_split
from metricon.features.leakage import (
    FitScope,
    audit_dependencies,
    audit_feature_names,
    audit_fit_scope,
    audit_preprocessing_manifest,
    prefix_invariance,
    preprocessing_manifest,
)


def test_planted_target_and_future_dependencies_are_rejected(rows):
    with pytest.raises(ValueError, match="unapproved"):
        audit_feature_names({"future_correct": 1})
    with pytest.raises(ValueError, match="future"):
        audit_dependencies("target", ["later"], {"target": 0, "later": 1})
    with pytest.raises(ValueError, match="current-unit"):
        audit_dependencies("target", ["same-bundle"], {"target": 0, "same-bundle": 0})
    assert prefix_invariance(rows, 4)["valid"]


def test_preprocessing_manifest_proves_training_scope(rows):
    split = forward_split(rows)
    manifest = preprocessing_manifest(split.assignments, split.hash)
    test = {identity for identity, value in split.assignments.items() if value == "test"}
    assert all(not test.intersection(entry["identities"]) for entry in manifest["components"])
    assert audit_preprocessing_manifest(manifest, split.assignments, split.hash)["valid"]
    identity = next(iter(test))
    with pytest.raises(ValueError, match="overlaps"):
        audit_fit_scope(FitScope("scaler", "train", (identity,), split.hash), split.assignments)


@pytest.mark.parametrize("alteration", ["empty", "omitted", "validation_vocabulary", "hash"])
def test_incomplete_or_misassigned_preprocessing_scopes_fail(rows, alteration):
    split = forward_split(rows)
    manifest = preprocessing_manifest(split.assignments, split.hash)
    if alteration == "empty":
        manifest["components"][0]["identities"] = []
    elif alteration == "omitted":
        manifest["components"].pop()
    elif alteration == "validation_vocabulary":
        manifest["components"][3]["fit_partition"] = "validation"
    else:
        manifest["components"][0]["identity_hash"] = "changed"
    with pytest.raises(ValueError):
        audit_preprocessing_manifest(manifest, split.assignments, split.hash)
