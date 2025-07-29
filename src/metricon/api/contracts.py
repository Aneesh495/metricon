from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceRequest(Request):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["user", "research"] = "user"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Workspace name cannot be blank")
        return value.strip()


class ImportOptionsRequest(Request):
    format: Literal["legacy", "csv", "ndjson", "parquet", "json"]
    namespace: str = Field(default="local", min_length=1, max_length=512)
    learner: str = Field(default="local-learner", min_length=1, max_length=512)


class ImportJobRequest(Request):
    upload_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    options: ImportOptionsRequest


class ExperimentRequest(Request):
    seed: int = 2026
    split: Literal["forward", "learner", "rolling"] = "forward"
    bootstrap_repetitions: int = Field(default=200, ge=20, le=5000)
    bkt_starts: int = Field(default=3, ge=1, le=10)
    bkt_max_iterations: int = Field(default=120, ge=1, le=500)
    online_updates: bool = True
    ablations: bool = True
    calibration: bool = True
    families: list[
        Literal["global", "item_prior", "recent", "logistic", "hierarchical", "bkt", "irt1", "irt2"]
    ] = Field(
        default_factory=lambda: [
            "global",
            "item_prior",
            "recent",
            "logistic",
            "hierarchical",
            "bkt",
            "irt1",
            "irt2",
        ],
        min_length=1,
        max_length=8,
    )
    rolling_folds: int = Field(default=3, ge=2, le=10)


class PlannerRequest(Request):
    learner_id: str
    budget_seconds: float = Field(default=900, gt=0, le=86400)
    maximum_actions: int = Field(default=12, ge=1, le=100)
    priorities: dict[str, float] = Field(default_factory=dict)
    prerequisites: dict[str, list[str]] = Field(default_factory=dict)
    prerequisite_threshold: float = Field(default=0.6, gt=0, lt=1)
    available_questions: list[str] = Field(default_factory=list)
    minimum_duration_observations: int = Field(default=3, ge=1, le=1000)
    recent_window: int = Field(default=10, ge=0, le=1000)
    model_artifact_id: str | None = None


class SimulationRequest(Request):
    seed: int = 2026
    repetitions: int = Field(default=200, ge=2, le=5000)
    budget_seconds: float = Field(default=900, gt=0, le=86400)
    skills: list[str] = Field(
        default_factory=lambda: ["algebra", "logic", "probability"], min_length=1, max_length=100
    )
    policies: list[Literal["random", "weakest", "uncertainty", "spaced", "budget"]] = Field(
        default_factory=lambda: ["random", "weakest", "uncertainty", "spaced", "budget"],
        min_length=1,
        max_length=5,
    )
    duration_seconds: dict[str, float] = Field(default_factory=dict)
    parameters: dict[str, dict[str, float]] = Field(default_factory=dict)
    assumed_duration_seconds: float = Field(default=60, gt=0, le=86400)
    trajectory_repetitions: int = Field(default=2, ge=0, le=5)
    regime: Literal["nominal", "slow_learning", "forgetting", "misspecified"] = "nominal"
    budget_mode: Literal["time", "questions"] = "time"
    question_budget: int = Field(default=15, ge=1, le=1000)


class DemoRequest(Request):
    seed: int = 2026
    learners: int = Field(default=50, ge=1, le=1000)
    attempts: int = Field(default=60, ge=1, le=1000)


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    kind: str
    dataset_id: str | None
    created_at: float


class JobResponse(BaseModel):
    id: str
    workspace_id: str
    dataset_id: str
    kind: str
    parameters: dict[str, Any]
    status: Literal["queued", "running", "completed", "failed", "canceled", "interrupted"]
    progress: float
    message: str
    result_id: str | None
    error: str | None
    cancel_requested: bool
    created_at: float
    updated_at: float
