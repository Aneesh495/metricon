from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from metricon.features.history import FEATURE_VERSION, HistoryFeatures, units
from metricon.schema.events import digest

NUMERIC_FEATURES = {
    "learner_log_attempts",
    "learner_rate",
    "item_log_attempts",
    "item_rate",
    "recent_rate",
    "recent_count",
    "cold_learner",
    "cold_item",
    "unknown_skill",
    "gap_unknown",
    "gap_log_seconds",
}
CATEGORICAL_FEATURES = {"kind"}
SKILL_PREFIXES = ("skill:", "prior_rate:", "prior_count:")
COMPONENT_FIT_PARTITIONS = {
    "model_parameters": "train",
    "item_priors": "train",
    "hierarchical_prior": "train",
    "feature_vocabulary": "train",
    "feature_scaler": "train",
    "hyperparameter_selection": "validation",
    "probability_calibration": "validation",
}


@dataclass(frozen=True)
class FitScope:
    component: str
    partition: str
    identities: tuple[str, ...]
    split_hash: str

    def manifest(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "fit_partition": self.partition,
            "identities": list(self.identities),
            "identity_hash": digest(sorted(self.identities)),
            "split_hash": self.split_hash,
            "feature_version": FEATURE_VERSION,
        }


def audit_fit_scope(
    scope: FitScope, assignments: dict[str, str], allowed_partition: str = "train"
) -> dict[str, Any]:
    if scope.partition != allowed_partition:
        raise ValueError("Preprocessing fit used an unauthorized split partition")
    if len(set(scope.identities)) != len(scope.identities):
        raise ValueError("Preprocessing fit scope repeats event identities")
    invalid = [
        identity for identity in scope.identities if assignments.get(identity) != allowed_partition
    ]
    if invalid:
        raise ValueError(f"Preprocessing overlaps held-out or unknown rows: {invalid[:5]}")
    return {
        "valid": True,
        "component": scope.component,
        "rows": len(scope.identities),
        "fit_partition": allowed_partition,
        "identity_hash": digest(sorted(scope.identities)),
    }


def audit_feature_names(features: dict[str, Any]) -> None:
    unknown = [
        name
        for name in features
        if name not in NUMERIC_FEATURES | CATEGORICAL_FEATURES
        and not name.startswith(SKILL_PREFIXES)
    ]
    if unknown:
        raise ValueError(f"Feature registry rejects unapproved target/future features: {unknown}")


def audit_dependencies(
    target: str, dependencies: list[str], unit_positions: dict[str, int]
) -> None:
    if target not in unit_positions:
        raise ValueError("Target is absent from chronological feature units")
    future = [
        identifier
        for identifier in dependencies
        if identifier not in unit_positions or unit_positions[identifier] >= unit_positions[target]
    ]
    if future:
        raise ValueError(
            f"Feature depends on current-unit, future, or unknown answers: {future[:5]}"
        )


def prefix_invariance(rows: list[dict[str, Any]], target_unit: int) -> dict[str, Any]:
    grouped = list(units(rows))
    if not 0 <= target_unit < len(grouped):
        raise ValueError("Prefix-invariance target is outside the history")
    original_features, original_rows = HistoryFeatures().transform(rows)
    altered = []
    targets = {row["identity"] for row in grouped[target_unit]}
    for index, group in enumerate(grouped):
        altered.extend(
            {**row, "correct": not row["correct"]} if index >= target_unit else dict(row)
            for row in group
        )
    changed_features, changed_rows = HistoryFeatures().transform(altered)
    original = {row["identity"]: feature for row, feature in zip(original_rows, original_features)}
    changed = {row["identity"]: feature for row, feature in zip(changed_rows, changed_features)}
    for identity in targets:
        audit_feature_names(original[identity])
        if original[identity] != changed[identity]:
            raise ValueError("Changing current/future answers changed a pre-target feature")
    return {
        "valid": True,
        "targets": len(targets),
        "target_unit": target_unit,
        "method": "Perturb every current and future outcome; compare exact target feature dictionaries",
    }


def preprocessing_manifest(assignments: dict[str, str], split_hash: str) -> dict[str, Any]:
    entries = []
    for partition, components in [
        (
            "train",
            [
                "model_parameters",
                "item_priors",
                "hierarchical_prior",
                "feature_vocabulary",
                "feature_scaler",
            ],
        ),
        ("validation", ["hyperparameter_selection", "probability_calibration"]),
    ]:
        identities = tuple(
            sorted(identity for identity, label in assignments.items() if label == partition)
        )
        for component in components:
            scope = FitScope(component, partition, identities, split_hash)
            audit_fit_scope(scope, assignments, partition)
            entries.append(scope.manifest())
    return {
        "version": "fit-scopes/1",
        "split_hash": split_hash,
        "components": entries,
        "test_policy": "Final test identities are absent from every fitting and selection scope",
    }


def audit_preprocessing_manifest(
    manifest: dict[str, Any], assignments: dict[str, str], split_hash: str
) -> dict[str, Any]:
    if manifest.get("split_hash") != split_hash:
        raise ValueError("Preprocessing scope refers to a different split")
    entries = manifest.get("components", [])
    names = [entry["component"] for entry in entries]
    if len(names) != len(set(names)) or set(names) != set(COMPONENT_FIT_PARTITIONS):
        raise ValueError("Preprocessing scope omits, repeats, or invents a required component")
    expected = {
        partition: {identity for identity, label in assignments.items() if label == partition}
        for partition in {"train", "validation"}
    }
    checked = []
    for entry in entries:
        partition = COMPONENT_FIT_PARTITIONS[entry["component"]]
        scope = FitScope(
            entry["component"],
            entry["fit_partition"],
            tuple(entry["identities"]),
            entry["split_hash"],
        )
        result = audit_fit_scope(scope, assignments, partition)
        if set(scope.identities) != expected[partition]:
            raise ValueError(
                "Preprocessing scope does not cover its exact authorized input partition"
            )
        if scope.split_hash != split_hash or result["identity_hash"] != entry["identity_hash"]:
            raise ValueError("Preprocessing scope identity or split digest was altered")
        if entry.get("feature_version") != FEATURE_VERSION:
            raise ValueError("Preprocessing scope uses a different feature contract")
        checked.append(result)
    return {"valid": True, "components": checked, "split_hash": split_hash}
