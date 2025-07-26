from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from datetime import datetime, timezone
from typing import Any, Literal

import pyarrow as pa
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "attempt/1"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def text_identifier(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Identifiers must be strings")
    value = unicodedata.normalize("NFC", value.strip())
    if not value or len(value) > 512 or any(ord(char) < 32 for char in value):
        raise ValueError("Identifier is empty, too long, or contains control characters")
    return value


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_hash: str
    adapter: str
    row: int = Field(ge=0)
    original_id: str | None = None
    identity_quality: Literal["stable", "position_only"] = "stable"
    note: str | None = None


class AttemptEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["attempt/1"] = SCHEMA_VERSION
    source_namespace: str
    event_id: str
    learner_id: str
    question_id: str
    skills: tuple[str, ...] = ()
    correct: bool
    attempt_kind: Literal["practice", "assessment", "review", "unknown"] = "unknown"
    source_sequence: int = Field(ge=0)
    timestamp: datetime | None = None
    duration_ms: float | None = Field(default=None, ge=0)
    session_id: str | None = None
    bundle_id: str | None = None
    order_scope: Literal["learner", "question"] = "learner"
    time_semantics: Literal["real", "shifted", "unknown"] = "unknown"
    duration_scope: Literal["event", "bundle", "unknown"] = "unknown"
    provenance: Provenance

    @field_validator("source_namespace", "event_id", "learner_id", "question_id", mode="before")
    @classmethod
    def identifiers(cls, value: Any) -> str:
        return text_identifier(value)

    @field_validator("correct", mode="before")
    @classmethod
    def boolean(cls, value: Any) -> bool:
        if type(value) is not bool:
            raise ValueError("correct must be a JSON boolean; integers and strings are invalid")
        return value

    @field_validator("source_sequence", mode="before")
    @classmethod
    def sequence(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("source_sequence must be an integer")
        return value

    @field_validator("skills", mode="before")
    @classmethod
    def tags(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("skills must be an array")
        return tuple(sorted(set(text_identifier(tag) for tag in value)))

    @field_validator("duration_ms", mode="before")
    @classmethod
    def duration(cls, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("duration_ms must be a finite number")
        if not math.isfinite(value):
            raise ValueError("duration_ms must be finite")
        return float(value)

    @field_validator("timestamp", mode="after")
    @classmethod
    def timestamp_zone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps require a timezone offset")
        return value.astimezone(timezone.utc)

    @field_validator("session_id", "bundle_id", mode="before")
    @classmethod
    def optional_identifier(cls, value: Any) -> str | None:
        return None if value is None else text_identifier(value)

    @model_validator(mode="after")
    def time_consistency(self) -> AttemptEvent:
        if self.timestamp is None and self.time_semantics != "unknown":
            raise ValueError("time semantics cannot be known without a timestamp")
        if self.duration_ms is None and self.duration_scope != "unknown":
            raise ValueError("duration scope cannot be known without a duration")
        return self

    @property
    def identity(self) -> str:
        return digest([self.source_namespace, self.event_id])

    @property
    def content_hash(self) -> str:
        return digest(self.model_dump(mode="json", exclude={"provenance"}))

    def arrow_row(self) -> dict[str, Any]:
        row = self.model_dump(exclude={"provenance"})
        row["skills"] = list(self.skills)
        row["provenance"] = canonical_json(self.provenance.model_dump())
        row["identity"] = self.identity
        row["content_hash"] = self.content_hash
        return row


ARROW_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("source_namespace", pa.string()),
        ("event_id", pa.string()),
        ("learner_id", pa.string()),
        ("question_id", pa.string()),
        ("skills", pa.list_(pa.string())),
        ("correct", pa.bool_()),
        ("attempt_kind", pa.string()),
        ("source_sequence", pa.int64()),
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("duration_ms", pa.float64()),
        ("session_id", pa.string()),
        ("bundle_id", pa.string()),
        ("order_scope", pa.string()),
        ("time_semantics", pa.string()),
        ("duration_scope", pa.string()),
        ("provenance", pa.string()),
        ("identity", pa.string()),
        ("content_hash", pa.string()),
    ]
)


def event_from_row(row: dict[str, Any]) -> AttemptEvent:
    data = {key: value for key, value in row.items() if key not in {"identity", "content_hash"}}
    if isinstance(data.get("provenance"), str):
        data["provenance"] = json.loads(data["provenance"])
    return AttemptEvent.model_validate(data)
