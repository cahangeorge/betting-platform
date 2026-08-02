"""Versioned, provider-scoped soccerdata ingestion contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Mapping

from app.providers.contracts import ProviderCapability

SOCCERDATA_ADAPTER_VERSION = "soccerdata-fork/6d0ccabc"
SOCCERDATA_JOB_SPEC_VERSION = "soccerdata-ingestion/v1"
SOCCERDATA_TRANSPORT_VERSION = "subprocess-json/v1"


class SoccerdataCacheMode(StrEnum):
    WARM = "warm"
    REFRESH = "refresh"
    NO_STORE = "no-store"


class SoccerdataJobMode(StrEnum):
    BACKFILL = "backfill"
    INCREMENTAL = "incremental"


@dataclass(frozen=True)
class SoccerdataOperation:
    key: str
    source_key: str
    bridge_operation: str
    capability: ProviderCapability
    worker_lane: str
    job_modes: frozenset[SoccerdataJobMode]
    freshness_seconds: int
    max_records: int
    max_payload_bytes: int
    default_chunk_size: int
    requests_per_minute: int
    completed_seasons_only: bool = False


SOCCERDATA_OPERATIONS: Mapping[str, SoccerdataOperation] = {
    operation.key: operation
    for operation in (
        SoccerdataOperation(
            key="matchhistory_results_backfill",
            source_key="football-data-co-uk",
            bridge_operation="matchhistory_games",
            capability=ProviderCapability.RESULTS,
            worker_lane="provider-http",
            job_modes=frozenset({SoccerdataJobMode.BACKFILL}),
            freshness_seconds=86_400,
            max_records=5_000,
            max_payload_bytes=16 * 1024 * 1024,
            default_chunk_size=250,
            requests_per_minute=10,
            completed_seasons_only=True,
        ),
        SoccerdataOperation(
            key="espn_schedule_incremental",
            source_key="espn",
            bridge_operation="espn_schedule",
            capability=ProviderCapability.FIXTURES,
            worker_lane="provider-http",
            job_modes=frozenset({SoccerdataJobMode.INCREMENTAL}),
            freshness_seconds=900,
            max_records=2_000,
            max_payload_bytes=8 * 1024 * 1024,
            default_chunk_size=200,
            requests_per_minute=30,
        ),
        SoccerdataOperation(
            key="fbref_schedule_backfill",
            source_key="fbref",
            bridge_operation="fbref_schedule",
            capability=ProviderCapability.FIXTURES,
            worker_lane="provider-browser",
            job_modes=frozenset({SoccerdataJobMode.BACKFILL}),
            freshness_seconds=86_400,
            max_records=2_000,
            max_payload_bytes=16 * 1024 * 1024,
            default_chunk_size=100,
            requests_per_minute=6,
        ),
        SoccerdataOperation(
            key="fbref_team_stats_backfill",
            source_key="fbref",
            bridge_operation="fbref_team_match_stats",
            capability=ProviderCapability.STATISTICS,
            worker_lane="provider-browser",
            job_modes=frozenset({SoccerdataJobMode.BACKFILL}),
            freshness_seconds=86_400,
            max_records=5_000,
            max_payload_bytes=24 * 1024 * 1024,
            default_chunk_size=100,
            requests_per_minute=6,
        ),
        SoccerdataOperation(
            key="understat_schedule_backfill",
            source_key="understat",
            bridge_operation="understat_schedule",
            capability=ProviderCapability.FIXTURES,
            worker_lane="provider-http",
            job_modes=frozenset({SoccerdataJobMode.BACKFILL}),
            freshness_seconds=21_600,
            max_records=2_000,
            max_payload_bytes=12 * 1024 * 1024,
            default_chunk_size=200,
            requests_per_minute=10,
        ),
        SoccerdataOperation(
            key="understat_team_stats_backfill",
            source_key="understat",
            bridge_operation="understat_team_match_stats",
            capability=ProviderCapability.STATISTICS,
            worker_lane="provider-http",
            job_modes=frozenset({SoccerdataJobMode.BACKFILL}),
            freshness_seconds=21_600,
            max_records=5_000,
            max_payload_bytes=16 * 1024 * 1024,
            default_chunk_size=200,
            requests_per_minute=10,
        ),
    )
}


@dataclass(frozen=True)
class SoccerdataIngestionSpec:
    operation: str
    competition: str
    season: str
    mode: SoccerdataJobMode
    cache_mode: SoccerdataCacheMode = SoccerdataCacheMode.WARM
    limit: int | None = None
    chunk_size: int | None = None
    page: int = 0
    start_cursor: int | None = None
    generation_key: str | None = None
    spec_version: str = SOCCERDATA_JOB_SPEC_VERSION

    def __post_init__(self) -> None:
        try:
            operation = SOCCERDATA_OPERATIONS[self.operation]
        except KeyError as exc:
            raise ValueError("Unsupported soccerdata ingestion operation") from exc
        try:
            object.__setattr__(self, "mode", SoccerdataJobMode(self.mode))
            object.__setattr__(self, "cache_mode", SoccerdataCacheMode(self.cache_mode))
        except ValueError as exc:
            raise ValueError("Invalid soccerdata ingestion mode") from exc
        if self.spec_version != SOCCERDATA_JOB_SPEC_VERSION:
            raise ValueError("Unsupported soccerdata job spec version")
        if self.mode not in operation.job_modes:
            raise ValueError("Soccerdata operation does not support the requested job mode")
        for label, value in (("competition", self.competition), ("season", self.season)):
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise ValueError(f"Soccerdata {label} must be a nonempty bounded string")
        limit = operation.max_records if self.limit is None else self.limit
        chunk_size = operation.default_chunk_size if self.chunk_size is None else self.chunk_size
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= operation.max_records:
            raise ValueError("Soccerdata limit exceeds the operation bound")
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or not 1 <= chunk_size <= limit:
            raise ValueError("Soccerdata chunk size must be positive and no larger than limit")
        object.__setattr__(self, "limit", limit)
        object.__setattr__(self, "chunk_size", chunk_size)
        if (
            isinstance(self.page, bool)
            or not isinstance(self.page, int)
            or not 0 <= self.page < (limit + chunk_size - 1) // chunk_size
        ):
            raise ValueError("Soccerdata page exceeds the bounded request")
        expected_offset = self.page * chunk_size
        if self.start_cursor is not None and (
            isinstance(self.start_cursor, bool)
            or not isinstance(self.start_cursor, int)
            or self.start_cursor != expected_offset
        ):
            raise ValueError("Soccerdata start cursor must match the immutable page")
        object.__setattr__(self, "start_cursor", expected_offset)
        if self.generation_key is not None and (
            not isinstance(self.generation_key, str)
            or len(self.generation_key) != 64
            or any(character not in "0123456789abcdef" for character in self.generation_key)
        ):
            raise ValueError("Soccerdata generation key must be a lowercase SHA-256 digest")
        if self.page == 0 and self.generation_key is not None:
            raise ValueError("Soccerdata initial page cannot supply an upstream generation")
        if self.page > 0 and self.generation_key is None:
            raise ValueError("Soccerdata continuation page requires an upstream generation")
        object.__setattr__(self, "competition", self.competition.strip())
        object.__setattr__(self, "season", self.season.strip())

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "SoccerdataIngestionSpec":
        allowed = {
            "spec_version",
            "operation",
            "competition",
            "season",
            "mode",
            "cache_mode",
            "limit",
            "chunk_size",
            "page",
            "start_cursor",
            "generation_key",
        }
        if set(config) - allowed:
            raise ValueError("Soccerdata ingestion config contains unsupported fields")
        try:
            return cls(
                spec_version=str(config.get("spec_version") or SOCCERDATA_JOB_SPEC_VERSION),
                operation=str(config["operation"]),
                competition=str(config["competition"]),
                season=str(config["season"]),
                mode=SoccerdataJobMode(config["mode"]),
                cache_mode=SoccerdataCacheMode(config.get("cache_mode", SoccerdataCacheMode.WARM)),
                limit=config.get("limit"),
                chunk_size=config.get("chunk_size"),
                page=config.get("page", 0),
                start_cursor=config.get("start_cursor"),
                generation_key=config.get("generation_key"),
            )
        except KeyError as exc:
            raise ValueError(f"Soccerdata ingestion config is missing {exc.args[0]}") from exc

    @property
    def operation_contract(self) -> SoccerdataOperation:
        return SOCCERDATA_OPERATIONS[self.operation]

    @property
    def task_type(self) -> str:
        suffix = "browser" if self.operation_contract.worker_lane == "provider-browser" else "http"
        return f"soccerdata_{suffix}_ingest"

    @property
    def request_fingerprint(self) -> str:
        payload = {
            "adapter_key": "soccerdata",
            "source_key": self.operation_contract.source_key,
            "operation": self.operation,
            "competition": self.competition,
            "season": self.season,
            "mode": self.mode.value,
            "limit": self.limit,
            "chunk_size": self.chunk_size,
            "page": self.page,
            "spec_version": self.spec_version,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    @property
    def group_fingerprint(self) -> str:
        """Stable aggregate identity shared by all immutable page specs."""
        payload = {
            "adapter_key": "soccerdata",
            "source_key": self.operation_contract.source_key,
            "operation": self.operation,
            "competition": self.competition,
            "season": self.season,
            "mode": self.mode.value,
            "limit": self.limit,
            "chunk_size": self.chunk_size,
            "spec_version": self.spec_version,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @property
    def spec_digest(self) -> str:
        encoded = json.dumps(self.to_config(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    def to_config(self) -> dict[str, Any]:
        config = {
            "spec_version": self.spec_version,
            "operation": self.operation,
            "competition": self.competition,
            "season": self.season,
            "mode": self.mode.value,
            "cache_mode": self.cache_mode.value,
            "limit": self.limit,
            "chunk_size": self.chunk_size,
            "page": self.page,
            "start_cursor": self.start_cursor,
        }
        if self.generation_key is not None:
            config["generation_key"] = self.generation_key
        return config

    def bridge_payload(self) -> dict[str, Any]:
        return {
            "operation": self.operation_contract.bridge_operation,
            "league": self.competition,
            "season": self.season,
            "limit": self.limit,
            "chunk_size": self.chunk_size,
            "page": self.page,
            "start_cursor": self.start_cursor,
            "source_key": self.operation_contract.source_key,
            "requests_per_minute": self.operation_contract.requests_per_minute,
            "ttl_seconds": self.operation_contract.freshness_seconds,
            "refresh": self.cache_mode is SoccerdataCacheMode.REFRESH,
            "no_store": self.cache_mode is SoccerdataCacheMode.NO_STORE,
        }

    def validate_source_window(self, *, now: datetime | None = None) -> None:
        if not self.operation_contract.completed_seasons_only:
            return
        current = (now or datetime.now(UTC)).astimezone(UTC)
        try:
            season_end_year = int(self.season.rsplit("-", 1)[1])
        except (IndexError, ValueError) as exc:
            raise ValueError("MatchHistory backfill requires a completed YYYY-YYYY season") from exc
        current_season_end_year = current.year + 1 if current.month >= 7 else current.year
        if season_end_year >= current_season_end_year:
            raise ValueError("MatchHistory is restricted to completed-season backfill")
