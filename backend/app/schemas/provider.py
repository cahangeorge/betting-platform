"""Safe, provider-agnostic runtime observability response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProviderRuntimeSourceResponse(BaseModel):
    """Source-scoped counters only; never provider request or payload data."""

    model_config = ConfigDict(extra="forbid")

    adapter_key: str = Field(min_length=1, max_length=63)
    source_key: str = Field(min_length=1, max_length=63)
    circuit_state: Literal["closed", "open", "half_open", "unknown", "not_applicable"]
    quota_limit: int | None = Field(default=None, ge=0)
    quota_reserved: int = Field(ge=0)
    quota_consumed: int = Field(ge=0)
    provider_remaining: int | None = Field(default=None, ge=0)
    consecutive_failures: int = Field(ge=0)
    last_reconciled_at: datetime | None = None
    observation_count: int = Field(ge=0)
    complete_snapshot_count: int = Field(ge=0)
    partial_snapshot_count: int = Field(ge=0)
    unmapped_observation_count: int = Field(ge=0)
    coverage_percent: float = Field(ge=0, le=100)
    latest_observed_at: datetime | None = None
    freshness_state: Literal["fresh", "stale", "no_data", "unknown"]
    cache_state: Literal["hit", "miss", "mixed", "not_applicable", "unknown"]


class ProviderLaneSnapshotResponse(BaseModel):
    """Bounded worker-lane counters without task arguments or error details."""

    model_config = ConfigDict(extra="forbid")

    lane: str = Field(min_length=1, max_length=64)
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    oldest_queue_age_ms: int = Field(ge=0)
    sampled_terminal_runs: int = Field(ge=0)
    retries: int = Field(ge=0)
    fallbacks: int = Field(ge=0)
    freshness_failures: int = Field(ge=0)
    peak_rss_bytes: int | None = Field(default=None, ge=0)
    peak_pid_count: int | None = Field(default=None, ge=0)


class ProviderRuntimeAlertResponse(BaseModel):
    """Stable alert code, deliberately excluding raw provider errors."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["source", "lane"]
    scope_key: str = Field(min_length=1, max_length=160)
    code: str = Field(min_length=1, max_length=96)
    severity: Literal["warning", "critical"]


class ProviderPipelinePhaseResponse(BaseModel):
    """Safe, aggregate progress for one provider-data pipeline phase."""

    model_config = ConfigDict(extra="forbid")

    phase: Literal["backfill", "normalize", "features", "model"]
    status: Literal["idle", "queued", "running", "attention"]
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    failed: int = Field(ge=0)
    partial: int = Field(ge=0)
    attention_count: int = Field(ge=0)


class ProviderRuntimeSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime
    sources: list[ProviderRuntimeSourceResponse]
    lanes: list[ProviderLaneSnapshotResponse]
    phases: list[ProviderPipelinePhaseResponse]
    alerts: list[ProviderRuntimeAlertResponse]
