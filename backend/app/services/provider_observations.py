# ruff: noqa: E501
"""Transactional persistence for immutable Provider Envelope observations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Mapping

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_observation import (
    ProviderObservation,
    ProviderObservationConflict,
    ProviderObservationDatasetLink,
    ProviderObservationQuarantine,
    ProviderObservationReceipt,
    ProviderObservationSlot,
)
from app.providers.contracts import (
    ProductionPolicy,
    ProviderEnvelopeQuarantine,
    ProviderExecutionContext,
    ProviderRecordEnvelope,
    ProviderRecordEnvelopeV2,
    ProviderSourceDescriptor,
)
from app.providers.odds import validate_odds_event_payload
from app.providers.registry import DEFAULT_PROVIDER_REGISTRY, ProviderRegistry, UnknownProviderError

_SENSITIVE = frozenset(
    {"authorization", "api_key", "apikey", "bearer", "cookie", "credential", "headers", "password", "secret", "token"}
)


class ProviderObservationPersistenceError(ValueError):
    """A record is valid enough to read but must not enter accepted storage."""


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    # Provider capability enums are StrEnum values and json serializes them.
    return value


def _canonical(value: object) -> str:
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ProviderObservationPersistenceError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _key(parts: list[object]) -> str:
    return _digest(_canonical(parts))


def _reject_sensitive(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if (
                not isinstance(key, str)
                or key.casefold() in _SENSITIVE
                or any(token in key.casefold() for token in _SENSITIVE)
            ):
                raise ProviderObservationPersistenceError("sensitive metadata is not accepted")
            _reject_sensitive(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_sensitive(item)


def _retention_until(
    *,
    context: ProviderExecutionContext | str,
    source_descriptor: ProviderSourceDescriptor,
    adapter_key: str,
    source_key: str,
    now: datetime,
) -> datetime:
    try:
        resolved_context = ProviderExecutionContext(context)
    except (TypeError, ValueError) as exc:
        raise ProviderObservationPersistenceError("provider execution context is invalid") from exc
    if resolved_context is ProviderExecutionContext.PRODUCTION:
        if (
            source_descriptor.adapter_key != adapter_key
            or source_descriptor.source_key != source_key
            or source_descriptor.production_policy is not ProductionPolicy.ALLOWED
            or source_descriptor.body_retention_days is None
        ):
            raise ProviderObservationPersistenceError("production source retention approval is required")
        return now + timedelta(days=source_descriptor.body_retention_days)
    return now + timedelta(days=30)


def _validate_payload(adapter_key: str, capability: str, schema_version: str, payload_json: str) -> None:
    """Fail-closed payload schema registry for accepted provider observations."""
    payload = json.loads(payload_json)
    if (capability, schema_version) == ("odds", "1.0"):
        if not isinstance(payload, dict):
            raise ProviderObservationPersistenceError("odds 1.0 payload must be an object")
        try:
            validate_odds_event_payload(payload)
        except ValueError as exc:
            raise ProviderObservationPersistenceError("odds 1.0 payload is invalid") from exc
        return
    if adapter_key == "soccerdata" and (capability, schema_version) in {
        ("fixtures", "1.0"),
        ("results", "1.0"),
        ("statistics", "1.0"),
    }:
        if not isinstance(payload, dict) or not payload:
            raise ProviderObservationPersistenceError("soccerdata 1.0 payload must be a nonempty object")
        if len(payload) > 128:
            raise ProviderObservationPersistenceError("soccerdata 1.0 payload has too many fields")
        return
    if (capability, schema_version) != ("predictions", "7.3"):
        raise ProviderObservationPersistenceError("unregistered provider capability payload schema")
    if not isinstance(payload, dict) or not payload:
        raise ProviderObservationPersistenceError("predictions 7.3 payload must be a nonempty object")
    allowed = {"home_goals", "away_goals"}
    if set(payload) - allowed or not any(key in payload for key in allowed):
        raise ProviderObservationPersistenceError("predictions 7.3 payload fields are invalid")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in payload.values()):
        raise ProviderObservationPersistenceError("predictions 7.3 payload values must be numeric")


async def persist_provider_envelope(
    session: AsyncSession,
    envelope: ProviderRecordEnvelope | ProviderRecordEnvelopeV2 | ProviderEnvelopeQuarantine,
    *,
    source_key: str | None = None,
    conversion_version: str | None = None,
    context: ProviderExecutionContext | str = ProviderExecutionContext.CANARY,
    source_descriptor: ProviderSourceDescriptor | None = None,
    registry: ProviderRegistry = DEFAULT_PROVIDER_REGISTRY,
    scrape_job_id: int | None = None,
    scheduled_job_run_id: int | None = None,
    origin_dataset_id: int | None = None,
    dataset_ids: tuple[int, ...] = (),
    reader_version: str = "provider-envelope-reader-v1",
    now: datetime | None = None,
) -> ProviderObservation | ProviderObservationQuarantine:
    """Persist one occurrence atomically, preserving replay and conflict evidence.

    The caller owns the outer transaction.  This function only uses savepoints
    for unique-race recovery, so a failed replay cannot partially create a fact.
    """
    received_at = _utc(now or datetime.now(UTC))
    if isinstance(envelope, ProviderEnvelopeQuarantine):
        return await quarantine_provider_envelope(session, envelope, reader_version=reader_version, now=received_at)

    if isinstance(envelope, ProviderRecordEnvelopeV2):
        adapter_key, resolved_source_key = envelope.adapter_key, envelope.source_key
        envelope_version, original_version = envelope.envelope_version, envelope.envelope_version
        converted_from_v1 = False
        resolved_conversion = None
        adapter_version, transport_version = envelope.adapter_version, envelope.transport_version
        provider_job_id, provider_run_id, correlation_id = envelope.job_id, envelope.run_id, envelope.correlation_id
        freshness, provenance = dict(envelope.freshness), dict(envelope.provenance)
    else:
        if not source_key or not conversion_version:
            return await quarantine_provider_envelope(
                session,
                ProviderEnvelopeQuarantine.from_raw(asdict(envelope), reason="missing_source_identity"),
                reader_version=reader_version,
                now=received_at,
            )
        adapter_key, resolved_source_key = envelope.provider_key, source_key
        envelope_version, original_version = "1.0", None
        converted_from_v1, resolved_conversion = True, conversion_version
        adapter_version, transport_version = "v1-conversion", "v1-conversion"
        provider_job_id, provider_run_id, correlation_id = "v1", "v1", "v1"
        freshness, provenance = {}, {}

    try:
        trusted_source = registry.get_source(adapter_key, resolved_source_key)
    except UnknownProviderError:
        return await quarantine_provider_envelope(
            session,
            ProviderEnvelopeQuarantine.from_raw(asdict(envelope), reason="untrusted_source_identity"),
            reader_version=reader_version,
            now=received_at,
        )
    if (
        trusted_source.adapter_key != adapter_key
        or trusted_source.source_key != resolved_source_key
        or not trusted_source.supports(envelope.capability)
        or (source_descriptor is not None and source_descriptor != trusted_source)
    ):
        return await quarantine_provider_envelope(
            session,
            ProviderEnvelopeQuarantine.from_raw(asdict(envelope), reason="untrusted_source_identity"),
            reader_version=reader_version,
            now=received_at,
        )

    try:
        _validate_payload(adapter_key, envelope.capability.value, envelope.schema_version, envelope.payload_json)
    except ProviderObservationPersistenceError as exc:
        reason = "unsupported_payload_schema" if "unregistered" in str(exc) else "invalid_payload"
        return await quarantine_provider_envelope(
            session,
            ProviderEnvelopeQuarantine.from_raw(asdict(envelope), reason=reason),
            reader_version=reader_version,
            now=received_at,
        )
    try:
        _reject_sensitive(json.loads(envelope.payload_json))
        _reject_sensitive(freshness)
        _reject_sensitive(provenance)
    except ProviderObservationPersistenceError:
        return await quarantine_provider_envelope(
            session,
            ProviderEnvelopeQuarantine.from_raw(asdict(envelope), reason="sensitive_metadata"),
            reader_version=reader_version,
            now=received_at,
        )
    body_until = _retention_until(
        context=context,
        source_descriptor=trusted_source,
        adapter_key=adapter_key,
        source_key=resolved_source_key,
        now=received_at,
    )
    observed_at = _utc(envelope.observed_at)
    capability = envelope.capability.value
    slot_key = _key(
        [
            adapter_key,
            resolved_source_key,
            capability,
            envelope.source_id,
            _timestamp(observed_at),
            envelope_version,
            envelope.schema_version,
        ]
    )
    observation_key = _key(
        [
            adapter_key,
            resolved_source_key,
            capability,
            envelope.source_id,
            _timestamp(observed_at),
            envelope_version,
            envelope.schema_version,
            envelope.payload_digest,
        ]
    )
    # v1 is retained as the exact canonical v1 representation; v2 received and
    # normalized representations are identical at this persistence boundary.
    normalized_envelope_json = _canonical(asdict(envelope))
    envelope_digest = _digest(normalized_envelope_json)
    freshness_json, provenance_json = _canonical(freshness), _canonical(provenance)

    # The slot row is deliberately created/locked before fact lookup. PostgreSQL
    # obtains a row lock here; on SQLite the enclosing write transaction gives
    # the equivalent serialization for tests.
    slot = await session.scalar(
        select(ProviderObservationSlot)
        .where(ProviderObservationSlot.observation_slot_key == slot_key)
        .with_for_update()
    )
    if slot is None:
        try:
            async with session.begin_nested():
                slot = ProviderObservationSlot(observation_slot_key=slot_key)
                session.add(slot)
                await session.flush()
        except IntegrityError:
            slot = await session.scalar(
                select(ProviderObservationSlot)
                .where(ProviderObservationSlot.observation_slot_key == slot_key)
                .with_for_update()
            )
            if slot is None:  # pragma: no cover - protects unusual isolation modes
                raise

    observation = await session.scalar(
        select(ProviderObservation).where(
            ProviderObservation.adapter_key == adapter_key,
            ProviderObservation.source_key == resolved_source_key,
            ProviderObservation.observation_key == observation_key,
        )
    )
    if observation is None:
        observation = ProviderObservation(
            slot_id=slot.id,
            adapter_key=adapter_key,
            source_key=resolved_source_key,
            capability=capability,
            source_id=envelope.source_id,
            envelope_version=envelope_version,
            original_envelope_version=original_version,
            schema_version=envelope.schema_version,
            converted_from_v1=converted_from_v1,
            conversion_version=resolved_conversion,
            observed_at=observed_at,
            ingested_at=received_at,
            freshness_json=freshness_json,
            provenance_json=provenance_json,
            payload_json=envelope.payload_json,
            envelope_json=normalized_envelope_json,
            payload_digest=envelope.payload_digest,
            envelope_digest=envelope_digest,
            observation_key=observation_key,
            observation_slot_key=slot_key,
            body_retention_until=body_until,
        )
        try:
            async with session.begin_nested():
                session.add(observation)
                await session.flush()
        except IntegrityError:
            observation = await session.scalar(
                select(ProviderObservation).where(
                    ProviderObservation.adapter_key == adapter_key,
                    ProviderObservation.source_key == resolved_source_key,
                    ProviderObservation.observation_key == observation_key,
                )
            )
            if observation is None:  # pragma: no cover
                raise

    siblings = list(
        (
            await session.scalars(
                select(ProviderObservation).where(ProviderObservation.observation_slot_key == slot_key)
            )
        ).all()
    )
    if any(
        sibling.id != observation.id and sibling.payload_digest != observation.payload_digest for sibling in siblings
    ):
        for sibling in siblings:
            if sibling.id == observation.id or sibling.payload_digest == observation.payload_digest:
                continue
            left_id, right_id = sorted((sibling.id, observation.id))
            existing = await session.scalar(
                select(ProviderObservationConflict.id).where(
                    ProviderObservationConflict.left_observation_id == left_id,
                    ProviderObservationConflict.right_observation_id == right_id,
                )
            )
            if existing is None:
                try:
                    async with session.begin_nested():
                        session.add(
                            ProviderObservationConflict(
                                observation_slot_key=slot_key,
                                left_observation_id=left_id,
                                right_observation_id=right_id,
                            )
                        )
                        await session.flush()
                except IntegrityError:
                    winner = await session.scalar(
                        select(ProviderObservationConflict.id).where(
                            ProviderObservationConflict.left_observation_id == left_id,
                            ProviderObservationConflict.right_observation_id == right_id,
                        )
                    )
                    if winner is None:
                        raise
        await session.execute(
            update(ProviderObservation)
            .where(ProviderObservation.observation_slot_key == slot_key)
            .values(conflict_state="conflicted")
        )
        slot.conflict_state = "conflicted"

    receipt_key = _key(
        [
            observation.observation_key,
            provider_job_id,
            provider_run_id,
            correlation_id,
            adapter_version,
            transport_version,
            resolved_conversion,
            envelope_digest,
            scrape_job_id,
            scheduled_job_run_id,
            origin_dataset_id,
        ]
    )
    if (
        await session.scalar(
            select(ProviderObservationReceipt.id).where(ProviderObservationReceipt.receipt_key == receipt_key)
        )
        is None
    ):
        try:
            async with session.begin_nested():
                session.add(
                    ProviderObservationReceipt(
                        observation_id=observation.id,
                        receipt_key=receipt_key,
                        provider_job_id=provider_job_id,
                        provider_run_id=provider_run_id,
                        correlation_id=correlation_id,
                        adapter_version=adapter_version,
                        transport_version=transport_version,
                        conversion_version=resolved_conversion,
                        received_envelope_json=normalized_envelope_json,
                        received_envelope_digest=envelope_digest,
                        received_at=received_at,
                        scrape_job_id_snapshot=scrape_job_id,
                        scheduled_job_run_id_snapshot=scheduled_job_run_id,
                        origin_dataset_id_snapshot=origin_dataset_id,
                        scrape_job_id=scrape_job_id,
                        scheduled_job_run_id=scheduled_job_run_id,
                        origin_dataset_id=origin_dataset_id,
                        body_retention_until=body_until,
                    )
                )
                await session.flush()
        except IntegrityError:
            winner = await session.scalar(
                select(ProviderObservationReceipt.id).where(ProviderObservationReceipt.receipt_key == receipt_key)
            )
            if winner is None:
                raise
    for dataset_id in set(dataset_ids):
        if (
            await session.scalar(
                select(ProviderObservationDatasetLink.id).where(
                    ProviderObservationDatasetLink.observation_id == observation.id,
                    ProviderObservationDatasetLink.dataset_id == dataset_id,
                )
            )
            is None
        ):
            try:
                async with session.begin_nested():
                    session.add(ProviderObservationDatasetLink(observation_id=observation.id, dataset_id=dataset_id))
                    await session.flush()
            except IntegrityError:
                winner = await session.scalar(
                    select(ProviderObservationDatasetLink.id).where(
                        ProviderObservationDatasetLink.observation_id == observation.id,
                        ProviderObservationDatasetLink.dataset_id == dataset_id,
                    )
                )
                if winner is None:
                    raise
    await session.flush()
    return observation


async def quarantine_provider_envelope(
    session: AsyncSession,
    envelope: ProviderEnvelopeQuarantine,
    *,
    reader_version: str,
    now: datetime | None = None,
) -> ProviderObservationQuarantine:
    """Store only a digest, stable reason and redacted diagnostics for invalid input."""
    received_at = _utc(now or datetime.now(UTC))
    existing = await session.scalar(
        select(ProviderObservationQuarantine).where(
            ProviderObservationQuarantine.raw_digest == envelope.raw_digest,
            ProviderObservationQuarantine.reason_code == envelope.reason,
            ProviderObservationQuarantine.reader_version == reader_version,
        )
    )
    if existing is not None:
        return existing
    row = ProviderObservationQuarantine(
        raw_digest=envelope.raw_digest,
        reason_code=envelope.reason,
        reader_version=reader_version,
        diagnostic_metadata=_canonical({"reason_code": envelope.reason}),
        received_at=received_at,
        metadata_retention_until=received_at + timedelta(days=30),
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        winner = await session.scalar(
            select(ProviderObservationQuarantine).where(
                ProviderObservationQuarantine.raw_digest == envelope.raw_digest,
                ProviderObservationQuarantine.reason_code == envelope.reason,
                ProviderObservationQuarantine.reader_version == reader_version,
            )
        )
        if winner is None:  # pragma: no cover
            raise
        return winner
    return row


async def purge_expired_provider_bodies(session: AsyncSession, *, now: datetime | None = None) -> tuple[int, int, int]:
    """Tombstone bodies while preserving all permanent digests and lineage keys."""
    moment = _utc(now or datetime.now(UTC))
    observations = await session.execute(
        update(ProviderObservation)
        .where(ProviderObservation.body_retention_until <= moment, ProviderObservation.body_purged_at.is_(None))
        .values(payload_json=None, envelope_json=None, body_purged_at=moment)
    )
    receipts = await session.execute(
        update(ProviderObservationReceipt)
        .where(
            ProviderObservationReceipt.body_retention_until <= moment,
            ProviderObservationReceipt.body_purged_at.is_(None),
        )
        .values(received_envelope_json=None, body_purged_at=moment)
    )
    quarantines = await session.execute(
        update(ProviderObservationQuarantine)
        .where(
            ProviderObservationQuarantine.metadata_retention_until <= moment,
            ProviderObservationQuarantine.metadata_purged_at.is_(None),
        )
        .values(diagnostic_metadata=None, metadata_purged_at=moment)
    )
    return observations.rowcount or 0, receipts.rowcount or 0, quarantines.rowcount or 0
