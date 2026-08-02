"""Strict versioned contracts for backend-owned penaltyblog model jobs."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MODEL_PIPELINE_CONTRACT_VERSION = "penaltyblog-model-pipeline/v1"
FEATURE_SET_SCHEMA_VERSION = "football-goals-features/v1"
FEATURE_SET_FIELDS_V1 = (
    "source_id",
    "observed_at",
    "date",
    "team_home",
    "team_away",
    "goals_home",
    "goals_away",
)
MODEL_ARTIFACT_MANIFEST_VERSION = "penaltyblog-model-artifact/v1"
REPRODUCIBLE_MODEL_ALLOWLIST = frozenset(
    {
        "PoissonGoalsModel",
        "DixonColesGoalModel",
        "BivariatePoissonGoalModel",
        "NegativeBinomialGoalModel",
        "ZeroInflatedPoissonGoalsModel",
    }
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FeatureSetSpecV1(StrictModel):
    schema_version: Literal["football-goals-features/v1"] = FEATURE_SET_SCHEMA_VERSION
    feature_set_key: str = Field(default="football-goals-core", min_length=1, max_length=100)
    fields: tuple[str, ...] = FEATURE_SET_FIELDS_V1
    null_policy: Literal["reject"] = "reject"
    timestamp_policy: Literal["utc"] = "utc"

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != FEATURE_SET_FIELDS_V1:
            raise ValueError("football-goals-features/v1 fields must match the supported ordered schema")
        return value


class ModelConfigV1(StrictModel):
    contract_version: Literal["penaltyblog-model-pipeline/v1"] = MODEL_PIPELINE_CONTRACT_VERSION
    model_class: str
    model_kwargs: dict[str, Any] = Field(default_factory=dict)
    fit_kwargs: dict[str, Any] = Field(default_factory=dict)
    max_goals: int = Field(default=10, ge=5, le=20)
    time_decay_xi: float | None = Field(default=None, gt=0, le=0.1)
    seed_policy: Literal["deterministic-no-rng"] = "deterministic-no-rng"

    @field_validator("model_class")
    @classmethod
    def validate_model_class(cls, value: str) -> str:
        if value not in REPRODUCIBLE_MODEL_ALLOWLIST:
            raise ValueError("model class is not approved for reproducible promotion")
        return value

    @field_validator("model_kwargs", "fit_kwargs")
    @classmethod
    def reject_nonfinite_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        def validate(item: Any) -> None:
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError("model config rejects non-finite numbers")
            if isinstance(item, dict):
                for key, nested in item.items():
                    if not isinstance(key, str):
                        raise ValueError("model config object keys must be strings")
                    validate(nested)
            elif isinstance(item, list):
                for nested in item:
                    validate(nested)
            elif item is not None and not isinstance(item, str | int | float | bool):
                raise ValueError("model config contains a non-JSON value")

        validate(value)
        return value

    @model_validator(mode="after")
    def validate_time_decay(self) -> ModelConfigV1:
        if self.time_decay_xi is not None and self.model_class != "DixonColesGoalModel":
            raise ValueError("time decay is approved only for DixonColesGoalModel")
        return self


class RuntimeFingerprintV1(StrictModel):
    runtime_version: Literal["penaltyblog-model-runtime/v1"] = "penaltyblog-model-runtime/v1"
    python_version: str = Field(min_length=1, max_length=64)
    penaltyblog_version: str = Field(min_length=1, max_length=64)
    penaltyblog_revision: str = Field(min_length=7, max_length=64)
    numpy_version: str = Field(min_length=1, max_length=64)
    scipy_version: str = Field(min_length=1, max_length=64)
    pandas_version: str = Field(min_length=1, max_length=64)
    lock_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    image_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    blas_threads: int = Field(default=1, ge=1, le=64)
    thread_environment: dict[
        Literal["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"], int
    ]
    reproducible_model_allowlist: tuple[str, ...]
    runtime_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("thread_environment")
    @classmethod
    def validate_thread_environment(cls, value: dict[str, int]) -> dict[str, int]:
        required = {"OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"}
        if set(value) != required or any(not 1 <= threads <= 64 for threads in value.values()):
            raise ValueError("runtime thread environment must contain exactly four positive bounded limits")
        return value


class ModelArtifactManifestV1(StrictModel):
    manifest_version: Literal["penaltyblog-model-artifact/v1"] = MODEL_ARTIFACT_MANIFEST_VERSION
    artifact_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    params_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    runtime_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    feature_set_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    training_data_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_config_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    training_rows: int = Field(gt=0)


class TrainModelCommandV1(StrictModel):
    contract_version: Literal["penaltyblog-model-pipeline/v1"] = MODEL_PIPELINE_CONTRACT_VERSION
    source_generation_id: int = Field(gt=0)
    feature_set: FeatureSetSpecV1 = Field(default_factory=FeatureSetSpecV1)
    model_spec: ModelConfigV1
    model_version: str = Field(min_length=1, max_length=100)
    training_cutoff_at: datetime

    @field_validator("training_cutoff_at")
    @classmethod
    def require_aware_cutoff(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("training cutoff must be timezone-aware")
        return value


class BacktestModelCommandV1(StrictModel):
    contract_version: Literal["penaltyblog-model-pipeline/v1"] = MODEL_PIPELINE_CONTRACT_VERSION
    model_artifact_id: int = Field(gt=0)
    source_generation_id: int = Field(gt=0)
    model_spec: ModelConfigV1
    training_cutoff_at: datetime
    test_started_at: datetime
    test_ended_at: datetime
    targets: tuple[PredictionTargetV1, ...] = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_window(self) -> BacktestModelCommandV1:
        values = (self.training_cutoff_at, self.test_started_at, self.test_ended_at)
        if any(value.tzinfo is None for value in values):
            raise ValueError("backtest timestamps must be timezone-aware")
        if not self.training_cutoff_at < self.test_started_at < self.test_ended_at:
            raise ValueError("backtest window must be strictly chronological")
        if any(not self.test_started_at <= target.forecast_at < self.test_ended_at for target in self.targets):
            raise ValueError("backtest targets must fall inside the declared test window")
        return self


class PredictionTargetV1(StrictModel):
    match_id: int = Field(gt=0)
    home_team: str = Field(min_length=1, max_length=255)
    away_team: str = Field(min_length=1, max_length=255)
    forecast_at: datetime
    kickoff_at: datetime
    odds_snapshot_id: int = Field(gt=0)
    odds_entry_id: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_forecast_window(self) -> PredictionTargetV1:
        if self.forecast_at.tzinfo is None or self.kickoff_at.tzinfo is None:
            raise ValueError("prediction timestamps must be timezone-aware")
        if self.forecast_at >= self.kickoff_at:
            raise ValueError("forecast must precede kickoff")
        return self


class PredictModelCommandV1(StrictModel):
    contract_version: Literal["penaltyblog-model-pipeline/v1"] = MODEL_PIPELINE_CONTRACT_VERSION
    model_artifact_id: int = Field(gt=0)
    source_generation_id: int = Field(gt=0)
    targets: tuple[PredictionTargetV1, ...] = Field(min_length=1, max_length=2_000)

    @field_validator("targets")
    @classmethod
    def unique_targets(cls, value: tuple[PredictionTargetV1, ...]) -> tuple[PredictionTargetV1, ...]:
        ids = [item.match_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("prediction target match IDs must be unique")
        return value
