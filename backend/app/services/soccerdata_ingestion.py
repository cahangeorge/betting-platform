"""Bounded, offline-testable soccerdata ingestion with durable checkpoints."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_identity import MatchProviderMapping
from app.models.provider_ingestion import (
    ProviderDatasetGeneration,
    ProviderDatasetGenerationPage,
    ProviderIngestionCheckpoint,
)
from app.models.provider_observation import ProviderObservation
from app.models.scrape import ScrapedDataset
from app.providers.contracts import ProviderExecutionContext, ProviderRecordEnvelopeV2
from app.providers.registry import DEFAULT_PROVIDER_REGISTRY, ProviderRegistry
from app.providers.soccerdata import SOCCERDATA_ADAPTER_VERSION, SOCCERDATA_TRANSPORT_VERSION, SoccerdataIngestionSpec
from app.services.provider_observations import persist_provider_envelope
from app.services.python_bridge import run_soccerdata

Bridge = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
Fence = Callable[[], Awaitable[None]]
_CACHE_MODES = frozenset({"cold", "warm", "revalidated", "no-store"})


class SoccerdataIngestionError(ValueError):
    """The bridge result is unsafe to persist or cannot form a complete dataset."""


@dataclass(frozen=True)
class SoccerdataIngestionResult:
    checkpoint_id: int
    state: str
    dataset_id: int | None
    record_count: int
    observation_count: int
    replayed: bool = False
    cursor: dict[str, Any] | None = None
    generation_id: int | None = None


@dataclass(frozen=True)
class SoccerdataBatch:
    rows: list[dict[str, Any]]
    cache: dict[str, Any]
    coverage_complete: bool
    cursor: dict[str, Any] | None


def authorize_soccerdata_ingestion(
    spec: SoccerdataIngestionSpec,
    *,
    registry: ProviderRegistry = DEFAULT_PROVIDER_REGISTRY,
    context: ProviderExecutionContext = ProviderExecutionContext.CANARY,
    now: datetime | None = None,
) -> None:
    """Fail closed before any external bridge work crosses the policy boundary."""
    spec.validate_source_window(now=now)
    registry.require_operation(
        "soccerdata",
        spec.operation_contract.source_key,
        spec.operation,
        context=context,
    )


async def fetch_soccerdata_batch(spec: SoccerdataIngestionSpec, bridge: Bridge = run_soccerdata) -> SoccerdataBatch:
    """Fetch and validate a bridge batch without touching database state."""
    rows, cache, coverage_complete, cursor = _validate_response(spec, await bridge(spec.bridge_payload()))
    return SoccerdataBatch(rows, cache, coverage_complete, cursor)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise SoccerdataIngestionError("bridge timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _database_utc(value: datetime) -> datetime:
    """Normalize database timestamps; SQLite drops timezone metadata in tests."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _timestamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise SoccerdataIngestionError(f"bridge {label} must be an ISO timestamp")
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise SoccerdataIngestionError(f"bridge {label} must be an ISO timestamp") from exc


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return _utc(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    return value


def _canonical(value: object) -> str:
    try:
        return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise SoccerdataIngestionError("bridge response must contain canonical JSON values") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _partition_key(spec: SoccerdataIngestionSpec) -> str:
    return f"{spec.operation}:{spec.competition}:{spec.season}:page:{spec.page}"


def _content_digest(rows: list[dict[str, Any]]) -> str:
    """Content identity excludes acquisition-derived observation timestamps."""
    return _digest([{"source_id": row["source_id"], "payload": row["payload"]} for row in rows])


def _advisory_lock_value(identity: str) -> int:
    return int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], byteorder="big", signed=True)


async def _acquire_identity_lock(session: AsyncSession, identity: str) -> None:
    """Serialize canonical dataset identities on PostgreSQL; SQLite tests stay portable."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:identity)"),
            {"identity": _advisory_lock_value(identity)},
        )


async def _published_dataset_id(
    session: AsyncSession,
    spec: SoccerdataIngestionSpec,
    payload_digest: str | None,
) -> int | None:
    if not payload_digest:
        return None
    return await session.scalar(
        select(ScrapedDataset.id).where(
            ScrapedDataset.dataset_key == _digest([spec.request_fingerprint, payload_digest]),
            ScrapedDataset.publication_state.in_(("staged", "published")),
        )
    )


async def _replayable_generation_id(
    session: AsyncSession,
    spec: SoccerdataIngestionSpec,
    generation_key: str | None,
    *,
    allow_staged: bool,
) -> int | None:
    if not generation_key:
        return None
    return await session.scalar(
        select(ProviderDatasetGeneration.id).where(
            ProviderDatasetGeneration.generation_key == generation_key,
            ProviderDatasetGeneration.dataset_group_key == spec.group_fingerprint,
            ProviderDatasetGeneration.state.in_(("staged", "published") if allow_staged else ("published",)),
        )
    )


def _validate_response(
    spec: SoccerdataIngestionSpec, response: object
) -> tuple[list[dict[str, Any]], dict[str, Any], bool, dict[str, Any] | None]:
    if (
        not isinstance(response, Mapping)
        or set(response) - {"rows", "summary", "cursor"}
        or not {"rows", "summary"} <= set(response)
    ):
        raise SoccerdataIngestionError("bridge response has unsupported or missing fields")
    if len(_canonical(response).encode()) > spec.operation_contract.max_payload_bytes:
        raise SoccerdataIngestionError("bridge response exceeds the operation payload bound")
    rows, summary, cursor = response["rows"], response["summary"], response.get("cursor")
    if not isinstance(rows, list) or len(rows) > spec.limit:
        raise SoccerdataIngestionError("bridge row count exceeds the requested bound")
    if not isinstance(summary, Mapping) or "cache" not in summary or "coverage_complete" not in summary:
        raise SoccerdataIngestionError("bridge summary is incomplete")
    cache, complete = summary["cache"], summary["coverage_complete"]
    if not isinstance(cache, Mapping) or set(cache) != {
        "mode",
        "as_of",
        "cache_hits",
        "upstream_requests",
        "artifact_digest",
    }:
        raise SoccerdataIngestionError("bridge cache telemetry is invalid")
    if (
        cache["mode"] not in _CACHE_MODES
        or any(
            isinstance(cache[key], bool) or not isinstance(cache[key], int) or cache[key] < 0
            for key in ("cache_hits", "upstream_requests")
        )
        or not isinstance(cache["artifact_digest"], str)
        or len(cache["artifact_digest"]) != 64
        or not isinstance(complete, bool)
    ):
        raise SoccerdataIngestionError("bridge cache telemetry is invalid")
    _timestamp(cache["as_of"], label="cache as_of")
    if cache["mode"] == "warm" and cache["upstream_requests"] != 0:
        raise SoccerdataIngestionError("warm cache response accessed upstream")
    if cursor is not None and (not isinstance(cursor, Mapping) or len(cursor) > 16):
        raise SoccerdataIngestionError("bridge cursor is invalid")

    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise SoccerdataIngestionError("bridge row must be an object")
        source_id = row.get("source_id") or row.get("id") or row.get("match_id")
        game_id = row.get("gameId")
        if source_id is None and game_id is not None:
            game_id = str(game_id).strip()
            source_id = game_id if game_id.startswith("event:") else f"event:{game_id}"
        elif source_id is not None and not isinstance(source_id, str):
            source_id = str(source_id)
        if source_id is None:
            identity = {key: row.get(key) for key in ("game", "date", "homeTeam", "awayTeam", "home_team", "away_team")}
            source_id = (
                f"derived:{_digest([spec.operation_contract.source_key, spec.competition, spec.season, identity])}"
            )
        if not isinstance(source_id, str) or not source_id.strip() or len(source_id) > 255:
            raise SoccerdataIngestionError("bridge row has no bounded source identity")
        observed_at = _timestamp(row.get("observed_at", cache["as_of"]), label="row observed_at")
        payload = (
            row.get("payload")
            if isinstance(row.get("payload"), Mapping)
            else {key: value for key, value in row.items() if key not in {"source_id", "id", "match_id", "observed_at"}}
        )
        if not payload:
            raise SoccerdataIngestionError("bridge row payload cannot be empty")
        _canonical(payload)
        normalized.append({"source_id": source_id.strip(), "observed_at": observed_at, "payload": dict(payload)})
    if cursor is not None and set(cursor) == {"page"} and cursor["page"] == spec.page + 1:
        cursor = {"page": cursor["page"], "start_cursor": spec.start_cursor + spec.chunk_size}
    if len(rows) < spec.chunk_size:
        cursor = None
    if cursor is not None and (
        set(cursor) != {"page", "start_cursor"}
        or cursor["page"] != spec.page + 1
        or cursor["start_cursor"] != spec.start_cursor + spec.chunk_size
        or len(normalized) != spec.chunk_size
    ):
        raise SoccerdataIngestionError("bridge cursor does not advance the immutable page")
    return normalized, dict(cache), complete, dict(cursor) if cursor is not None else None


async def _claim(
    session: AsyncSession, spec: SoccerdataIngestionSpec, run_id: str | None, *, now: datetime
) -> tuple[ProviderIngestionCheckpoint, bool]:
    checkpoint = await session.scalar(
        select(ProviderIngestionCheckpoint)
        .where(
            ProviderIngestionCheckpoint.spec_digest == spec.spec_digest,
            ProviderIngestionCheckpoint.partition_key == _partition_key(spec),
        )
        .with_for_update()
    )
    if checkpoint is None:
        checkpoint = ProviderIngestionCheckpoint(
            checkpoint_key=_digest([spec.spec_digest, _partition_key(spec)]),
            spec_digest=spec.spec_digest,
            spec_version=spec.spec_version,
            partition_key=_partition_key(spec),
            state="claimed",
            run_id_snapshot=run_id,
            claim_token=secrets.token_hex(16),
        )
        try:
            async with session.begin_nested():
                session.add(checkpoint)
                await session.flush()
        except IntegrityError:
            checkpoint = await session.scalar(
                select(ProviderIngestionCheckpoint)
                .where(
                    ProviderIngestionCheckpoint.spec_digest == spec.spec_digest,
                    ProviderIngestionCheckpoint.partition_key == _partition_key(spec),
                )
                .with_for_update()
            )
            if checkpoint is None:  # pragma: no cover - protects unusual isolation modes
                raise
    if (
        checkpoint.state in {"completed", "no_data"}
        and checkpoint.fresh_until is not None
        and _database_utc(checkpoint.fresh_until) > now
    ):
        generation_id = await _replayable_generation_id(
            session,
            spec,
            checkpoint.dataset_generation_key,
            allow_staged=checkpoint.cursor_json is not None,
        )
        dataset_id = (
            await _published_dataset_id(session, spec, checkpoint.payload_digest)
            if checkpoint.state == "completed"
            else None
        )
        if generation_id is not None and (checkpoint.state == "no_data" or dataset_id is not None):
            return checkpoint, True
    if checkpoint.state != "claimed" or checkpoint.run_id_snapshot != run_id:
        checkpoint.state, checkpoint.attempt = "claimed", checkpoint.attempt + 1
        checkpoint.run_id_snapshot, checkpoint.claim_token, checkpoint.error = run_id, secrets.token_hex(16), None
        await session.flush()
    return checkpoint, False


async def _replay_result(
    session: AsyncSession,
    spec: SoccerdataIngestionSpec,
    *,
    now: datetime,
) -> SoccerdataIngestionResult | None:
    checkpoint = await session.scalar(
        select(ProviderIngestionCheckpoint).where(
            ProviderIngestionCheckpoint.spec_digest == spec.spec_digest,
            ProviderIngestionCheckpoint.partition_key == _partition_key(spec),
            ProviderIngestionCheckpoint.state.in_(("completed", "no_data")),
            ProviderIngestionCheckpoint.fresh_until > now,
        )
    )
    if checkpoint is None:
        return None
    dataset_id = (
        await _published_dataset_id(session, spec, checkpoint.payload_digest)
        if checkpoint.state == "completed"
        else None
    )
    if checkpoint.state == "completed" and dataset_id is None:
        return None
    generation_id = await _replayable_generation_id(
        session,
        spec,
        checkpoint.dataset_generation_key,
        allow_staged=checkpoint.cursor_json is not None,
    )
    if generation_id is None:
        return None
    return SoccerdataIngestionResult(
        checkpoint.id,
        checkpoint.state,
        dataset_id,
        checkpoint.record_count or 0,
        checkpoint.observation_count or 0,
        True,
        checkpoint.cursor_json,
        generation_id,
    )


async def replay_soccerdata_batch(
    session: AsyncSession, spec: SoccerdataIngestionSpec, *, now: datetime | None = None
) -> SoccerdataIngestionResult | None:
    """Read a fresh completed page before deciding whether a bridge fetch is needed."""
    return await _replay_result(session, spec, now=_utc(now or datetime.now(UTC)))


async def close_soccerdata_replay_transaction(session: AsyncSession) -> None:
    """Release the read-only replay transaction before an external fetch.

    SQLAlchemy autobegins a transaction for the checkpoint replay ``SELECT``.
    A replay miss must not retain that transaction while the bridge performs
    network I/O: apart from extending the transaction needlessly, it can keep
    a stale snapshot across a long multi-page acquisition.  Replay writes are
    deliberately absent, so rollback is the correct and least-surprising
    boundary rather than commit.
    """
    if getattr(session, "in_transaction", lambda: False)():
        await session.rollback()


async def _require_current_match_mappings(
    session: AsyncSession,
    *,
    source_key: str,
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        mapping = await session.scalar(
            select(MatchProviderMapping.id).where(
                MatchProviderMapping.adapter_key == "soccerdata",
                MatchProviderMapping.source_key == source_key,
                MatchProviderMapping.source_id == row["source_id"],
                MatchProviderMapping.state == "accepted",
                MatchProviderMapping.valid_to.is_(None),
            )
        )
        if mapping is None:
            raise SoccerdataIngestionError("dataset record has no accepted current match identity mapping")


async def _ensure_generation(
    session: AsyncSession,
    spec: SoccerdataIngestionSpec,
    *,
    generation_key: str,
    artifact_digest: str,
    source_as_of: datetime,
    fresh_until: datetime,
) -> ProviderDatasetGeneration:
    await _acquire_identity_lock(session, f"soccerdata-generation:{generation_key}")
    generation = await session.scalar(
        select(ProviderDatasetGeneration).where(ProviderDatasetGeneration.generation_key == generation_key)
    )
    if generation is None:
        generation = ProviderDatasetGeneration(
            generation_key=generation_key,
            dataset_group_key=spec.group_fingerprint,
            artifact_digest=artifact_digest,
            state="staged",
            source_as_of=source_as_of,
            fresh_until=fresh_until,
        )
        session.add(generation)
        await session.flush()
    elif generation.dataset_group_key != spec.group_fingerprint or generation.artifact_digest != artifact_digest:
        raise SoccerdataIngestionError("upstream generation identity conflicts with persisted lineage")
    else:
        if _database_utc(generation.source_as_of) < source_as_of:
            generation.source_as_of = source_as_of
        if _database_utc(generation.fresh_until) < fresh_until:
            generation.fresh_until = fresh_until
    return generation


async def _attach_generation_page(
    session: AsyncSession,
    generation: ProviderDatasetGeneration,
    *,
    page: int,
    dataset_id: int,
) -> None:
    membership = await session.scalar(
        select(ProviderDatasetGenerationPage).where(
            ProviderDatasetGenerationPage.generation_id == generation.id,
            ProviderDatasetGenerationPage.page == page,
        )
    )
    if membership is not None:
        if membership.dataset_id != dataset_id:
            raise SoccerdataIngestionError("upstream generation page has conflicting canonical content")
        return
    session.add(ProviderDatasetGenerationPage(generation_id=generation.id, page=page, dataset_id=dataset_id))
    await session.flush()


async def _publish_generation(
    session: AsyncSession,
    spec: SoccerdataIngestionSpec,
    generation_key: str,
    *,
    terminal_has_dataset: bool,
) -> None:
    """Atomically advance the logical head after exact generation continuity."""
    await _acquire_identity_lock(session, f"soccerdata-group:{spec.group_fingerprint}")
    generations = (
        await session.scalars(
            select(ProviderDatasetGeneration)
            .where(ProviderDatasetGeneration.dataset_group_key == spec.group_fingerprint)
            .with_for_update()
        )
    ).all()
    current = next((item for item in generations if item.generation_key == generation_key), None)
    if current is None:
        raise SoccerdataIngestionError("terminal page has no persisted upstream generation")
    pages = set(
        (
            await session.scalars(
                select(ProviderDatasetGenerationPage.page).where(
                    ProviderDatasetGenerationPage.generation_id == current.id
                )
            )
        ).all()
    )
    expected_pages = set(range(spec.page + (1 if terminal_has_dataset else 0)))
    if pages != expected_pages:
        raise SoccerdataIngestionError("terminal page cannot publish an incomplete staged page group")
    published = next((item for item in generations if item.state == "published" and item.id != current.id), None)
    if published is not None and _database_utc(published.source_as_of) >= _database_utc(current.source_as_of):
        raise SoccerdataIngestionError("stale upstream generation cannot replace the published head")
    if published is not None:
        published.state = "superseded"
        await session.flush()
    current.state = "published"
    current.terminal_page = spec.page if terminal_has_dataset else spec.page - 1
    datasets = (
        await session.scalars(
            select(ScrapedDataset)
            .join(ProviderDatasetGenerationPage, ProviderDatasetGenerationPage.dataset_id == ScrapedDataset.id)
            .where(ProviderDatasetGenerationPage.generation_id == current.id)
        )
    ).all()
    for dataset in datasets:
        dataset.publication_state = "published"


async def ingest_soccerdata(
    session: AsyncSession,
    spec: SoccerdataIngestionSpec,
    *,
    bridge: Bridge = run_soccerdata,
    registry: ProviderRegistry = DEFAULT_PROVIDER_REGISTRY,
    context: ProviderExecutionContext = ProviderExecutionContext.CANARY,
    fence: Fence | None = None,
    job_id: str = "soccerdata-ingestion",
    run_id: str | None = None,
    correlation_id: str = "soccerdata-ingestion",
    scheduled_job_run_id: int | None = None,
    require_identity_mappings: bool = True,
    now: datetime | None = None,
    batch: SoccerdataBatch | None = None,
) -> SoccerdataIngestionResult:
    """Ingest a complete bridge partition; policy is always enforced before bridge work."""
    authorize_soccerdata_ingestion(spec, registry=registry, context=context, now=now)
    effective_now = _utc(now or datetime.now(UTC))
    # A caller may be composing multiple persistence operations in one unit of
    # work.  We may close the transaction opened by our replay SELECT, but we
    # must never roll back a transaction that was already active on entry.
    caller_owned_transaction = session.in_transaction()
    replay = await _replay_result(session, spec, now=effective_now)
    if replay is not None:
        return replay
    if batch is None:
        if caller_owned_transaction:
            raise SoccerdataIngestionError(
                "external soccerdata fetch requires a clean session; "
                "finish the caller transaction or provide a pre-fetched batch"
            )
        await close_soccerdata_replay_transaction(session)
        try:
            batch = await fetch_soccerdata_batch(spec, bridge)
        except Exception as exc:
            checkpoint, _ = await _claim(session, spec, run_id, now=effective_now)
            checkpoint.state, checkpoint.error = "failed", str(exc)[:1_000]
            await session.flush()
            raise
    return await persist_soccerdata_batch(
        session,
        spec,
        batch,
        registry=registry,
        context=context,
        fence=fence,
        job_id=job_id,
        run_id=run_id,
        correlation_id=correlation_id,
        scheduled_job_run_id=scheduled_job_run_id,
        require_identity_mappings=require_identity_mappings,
        now=now,
    )


async def persist_soccerdata_batch(
    session: AsyncSession,
    spec: SoccerdataIngestionSpec,
    batch: SoccerdataBatch,
    *,
    registry: ProviderRegistry = DEFAULT_PROVIDER_REGISTRY,
    context: ProviderExecutionContext = ProviderExecutionContext.CANARY,
    fence: Fence | None = None,
    job_id: str = "soccerdata-ingestion",
    run_id: str | None = None,
    correlation_id: str = "soccerdata-ingestion",
    scheduled_job_run_id: int | None = None,
    require_identity_mappings: bool = True,
    now: datetime | None = None,
) -> SoccerdataIngestionResult:
    """Persist a previously fetched immutable batch; suitable for fenced runners."""
    spec.validate_source_window(now=now)
    effective_now = _utc(now or datetime.now(UTC))
    source = registry.require_operation(
        "soccerdata", spec.operation_contract.source_key, spec.operation, context=context
    )
    checkpoint, replayed = await _claim(session, spec, run_id, now=effective_now)
    if replayed:
        dataset_id = (
            await _published_dataset_id(session, spec, checkpoint.payload_digest)
            if checkpoint.state == "completed"
            else None
        )
        generation_id = await _replayable_generation_id(
            session,
            spec,
            checkpoint.dataset_generation_key,
            allow_staged=checkpoint.cursor_json is not None,
        )
        if generation_id is None:
            raise SoccerdataIngestionError("checkpoint has no replayable canonical generation")
        return SoccerdataIngestionResult(
            checkpoint.id,
            checkpoint.state,
            dataset_id,
            checkpoint.record_count or 0,
            checkpoint.observation_count or 0,
            True,
            checkpoint.cursor_json,
            generation_id,
        )
    try:
        rows, cache, coverage_complete, cursor = batch.rows, batch.cache, batch.coverage_complete, batch.cursor
        if fence is not None:
            await fence()
        cache_as_of = _timestamp(cache["as_of"], label="cache as_of")
        if cache_as_of + timedelta(seconds=spec.operation_contract.freshness_seconds) <= effective_now:
            raise SoccerdataIngestionError("bridge cache as_of is already expired")
        if cache_as_of > effective_now + timedelta(minutes=5):
            raise SoccerdataIngestionError("bridge cache as_of exceeds future skew")
        checkpoint.cursor_json, checkpoint.cache_mode, checkpoint.cache_as_of = cursor, str(cache["mode"]), cache_as_of
        checkpoint.fresh_until = cache_as_of + timedelta(seconds=spec.operation_contract.freshness_seconds)
        # Canonical content identity must not change only because acquisition
        # telemetry (cache mode/as_of/request counts) changed.
        checkpoint.payload_digest, checkpoint.record_count = _content_digest(rows), len(rows)
        generation_key = _digest([spec.group_fingerprint, cache["artifact_digest"]])
        if spec.generation_key is not None and spec.generation_key != generation_key:
            raise SoccerdataIngestionError("bridge artifact changed during the immutable page generation")
        checkpoint.dataset_generation_key = generation_key
        if cursor is not None:
            cursor = {**cursor, "generation_key": generation_key}
            checkpoint.cursor_json = cursor
        if not coverage_complete:
            raise SoccerdataIngestionError("bridge coverage is incomplete")
        generation = await _ensure_generation(
            session,
            spec,
            generation_key=generation_key,
            artifact_digest=str(cache["artifact_digest"]),
            source_as_of=cache_as_of,
            fresh_until=checkpoint.fresh_until,
        )
        if not rows:
            checkpoint.state, checkpoint.observation_count = "no_data", 0
            if cursor is None:
                await _publish_generation(session, spec, generation_key, terminal_has_dataset=False)
            await session.flush()
            return SoccerdataIngestionResult(checkpoint.id, "no_data", None, 0, 0, False, cursor, generation.id)
        dataset_key = _digest([spec.request_fingerprint, checkpoint.payload_digest])
        await _acquire_identity_lock(session, f"soccerdata-dataset:{dataset_key}")
        existing_dataset = await session.scalar(select(ScrapedDataset).where(ScrapedDataset.dataset_key == dataset_key))
        if existing_dataset is not None:
            if require_identity_mappings:
                await _require_current_match_mappings(session, source_key=source.source_key, rows=rows)
            if fence is not None:
                await fence()
            checkpoint.state = "completed"
            checkpoint.observation_count = checkpoint.observation_count or len(rows)
            if existing_dataset.source_as_of is None or _database_utc(existing_dataset.source_as_of) < cache_as_of:
                existing_dataset.source_as_of = cache_as_of
            if (
                existing_dataset.fresh_until is None
                or _database_utc(existing_dataset.fresh_until) < checkpoint.fresh_until
            ):
                existing_dataset.fresh_until = checkpoint.fresh_until
            existing_dataset.data = {**existing_dataset.data, "cache": cache}
            await _attach_generation_page(session, generation, page=spec.page, dataset_id=existing_dataset.id)
            if cursor is None:
                await _publish_generation(session, spec, generation_key, terminal_has_dataset=True)
            await session.flush()
            return SoccerdataIngestionResult(
                checkpoint.id,
                "completed",
                existing_dataset.id,
                len(rows),
                checkpoint.observation_count,
                False,
                cursor,
                generation.id,
            )
        async with session.begin_nested():
            dataset = ScrapedDataset(
                name=f"soccerdata:{spec.operation}:{spec.competition}:{spec.season}",
                source="soccerdata",
                data={
                    "spec": spec.to_config(),
                    "request_fingerprint": spec.request_fingerprint,
                    "group_fingerprint": spec.group_fingerprint,
                    "checkpoint_key": checkpoint.checkpoint_key,
                    "cache": cache,
                    "rows": _json_value(rows),
                },
                matches_count=len(rows),
                dataset_key=dataset_key,
                dataset_group_key=spec.group_fingerprint,
                dataset_schema_version="1.0",
                dataset_digest=checkpoint.payload_digest,
                origin_scheduled_job_run_id=scheduled_job_run_id,
                origin_run_id_snapshot=run_id,
                source_as_of=cache_as_of,
                fresh_until=checkpoint.fresh_until,
            )
            session.add(dataset)
            await session.flush()
            observations = []
            for row in rows:
                envelope = ProviderRecordEnvelopeV2.from_payload(
                    adapter_key="soccerdata",
                    source_key=source.source_key,
                    capability=spec.operation_contract.capability,
                    source_id=row["source_id"],
                    observed_at=row["observed_at"],
                    payload=row["payload"],
                    adapter_version=SOCCERDATA_ADAPTER_VERSION,
                    transport_version=SOCCERDATA_TRANSPORT_VERSION,
                    job_id=job_id,
                    run_id=run_id or checkpoint.claim_token or "soccerdata-ingestion",
                    correlation_id=correlation_id,
                    freshness={"as_of": cache["as_of"], "ttl_seconds": spec.operation_contract.freshness_seconds},
                    provenance={"source_revision": spec.spec_version},
                    schema_version="1.0",
                )
                observations.append(
                    await persist_provider_envelope(
                        session, envelope, registry=registry, context=context, dataset_ids=(dataset.id,), now=now
                    )
                )
            if not all(
                isinstance(observation, ProviderObservation) and observation.conflict_state != "conflicted"
                for observation in observations
            ):
                raise SoccerdataIngestionError("all dataset observations must be accepted and non-conflicted")
            if require_identity_mappings:
                await _require_current_match_mappings(session, source_key=source.source_key, rows=rows)
            if fence is not None:
                await fence()
            dataset.publication_state = "staged"
            await session.flush()
            await _attach_generation_page(session, generation, page=spec.page, dataset_id=dataset.id)
        checkpoint.state, checkpoint.observation_count = "completed", len(observations)
        if cursor is None:
            await _publish_generation(session, spec, generation_key, terminal_has_dataset=True)
        await session.flush()
        return SoccerdataIngestionResult(
            checkpoint.id,
            "completed",
            dataset.id,
            len(rows),
            len(observations),
            False,
            cursor,
            generation.id,
        )
    except Exception as exc:
        checkpoint.state, checkpoint.error = "failed", str(exc)[:1_000]
        await session.flush()
        raise
