"""Disabled-by-default, quota-accounted Sportmonks odds acquisition.

This service is deliberately not a scheduler or public endpoint.  It supplies
the one ordered acquisition path that a future approved provider-http worker
can call: authorization, credentials, quota/circuit reservation, HTTP adapter,
and exactly-once reconciliation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.provider_observation import ProviderObservation, ProviderObservationReceipt
from app.providers.contracts import ProviderExecutionContext, ProviderRecordEnvelopeV2
from app.providers.registry import DEFAULT_PROVIDER_REGISTRY, ProviderPolicyError, ProviderRegistry
from app.providers.sportmonks_odds import (
    SPORTMONKS_ADAPTER_KEY,
    SPORTMONKS_SOURCE_KEY,
    SportmonksOddsAdapter,
    SportmonksOddsAdapterError,
)
from app.services.provider_observations import persist_provider_envelope
from app.services.provider_runtime import (
    ProviderRuntimeUnavailableError,
    configure_provider_quota,
    reap_expired_provider_reservations,
    reconcile_provider_reservation,
    reserve_provider_quota,
)


class LicensedOddsAcquisitionStatus(StrEnum):
    ACQUIRED = "acquired"
    DENIED = "denied"
    FAILED = "failed"


@dataclass(frozen=True)
class LicensedOddsTelemetry:
    """Secret-free outcome metadata suitable for structured worker telemetry."""

    adapter_key: str
    source_key: str
    scope: str
    status: LicensedOddsAcquisitionStatus
    reason_code: str
    charged: bool
    failure: bool
    record_count: int


@dataclass(frozen=True)
class LicensedOddsAcquisition:
    """Typed, non-throwing outcome for expected admission and upstream failures."""

    records: tuple[ProviderRecordEnvelopeV2, ...]
    telemetry: LicensedOddsTelemetry
    observation_ids: tuple[int, ...] = ()
    replayed: bool = False


class _SportmonksFetcher(Protocol):
    async def fetch_latest_odds(
        self,
        *,
        scope: str,
        job_id: str,
        run_id: str,
        correlation_id: str,
        context: ProviderExecutionContext,
        observed_at: datetime | None = None,
    ) -> tuple[ProviderRecordEnvelopeV2, ...]: ...


def _credential_present(settings: Settings) -> bool:
    token = settings.sportmonks_api_token
    return token is not None and bool(token.get_secret_value().strip())


def _telemetry(
    *,
    scope: str,
    status: LicensedOddsAcquisitionStatus,
    reason_code: str,
    charged: bool = False,
    failure: bool = False,
    record_count: int = 0,
) -> LicensedOddsTelemetry:
    return LicensedOddsTelemetry(
        adapter_key=SPORTMONKS_ADAPTER_KEY,
        source_key=SPORTMONKS_SOURCE_KEY,
        scope=scope,
        status=status,
        reason_code=reason_code,
        charged=charged,
        failure=failure,
        record_count=record_count,
    )


def _reservation_key(*, scope: str, job_id: str, run_id: str, correlation_id: str) -> str:
    """Stable across execution-fence retries, but unique to one acquisition."""

    payload = {
        "adapter_key": SPORTMONKS_ADAPTER_KEY,
        "source_key": SPORTMONKS_SOURCE_KEY,
        "operation": "fetch_latest_odds",
        "scope": scope,
        "job_id": job_id,
        "run_id": run_id,
        "correlation_id": correlation_id,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class LicensedOddsService:
    """Acquires Sportmonks odds only after all local admission controls pass."""

    def __init__(
        self,
        settings: Settings,
        *,
        registry: ProviderRegistry = DEFAULT_PROVIDER_REGISTRY,
        transport: httpx.AsyncBaseTransport | None = None,
        adapter: _SportmonksFetcher | None = None,
        circuit_open_seconds: int = 60,
    ) -> None:
        if circuit_open_seconds < 1:
            raise ValueError("circuit_open_seconds must be positive")
        self._settings = settings
        self._registry = registry
        self._adapter: _SportmonksFetcher = adapter or SportmonksOddsAdapter(
            settings, registry=registry, transport=transport
        )
        self._circuit_open_seconds = circuit_open_seconds

    async def acquire_sportmonks_latest(
        self,
        session: AsyncSession,
        *,
        scope: str,
        job_id: str,
        run_id: str,
        correlation_id: str,
        context: ProviderExecutionContext = ProviderExecutionContext.PRODUCTION,
        observed_at: datetime | None = None,
        execution_token: str | None = None,
        scheduled_job_run_id: int | None = None,
    ) -> LicensedOddsAcquisition:
        """Run one crash-safe admitted batch using a dedicated clean session.

        The method owns only provider-runtime commits.  Callers must not place
        unrelated pending work in ``session``.  Admission is committed before
        egress; reconciliation is committed afterward in a fresh transaction.
        """

        normalized_scope = str(scope).strip().casefold()
        try:
            source = self._registry.require_operation(
                SPORTMONKS_ADAPTER_KEY,
                SPORTMONKS_SOURCE_KEY,
                "fetch_latest_odds",
                context=context,
            )
        except (ProviderPolicyError, ValueError, LookupError):
            return LicensedOddsAcquisition(
                records=(),
                telemetry=_telemetry(
                    scope=normalized_scope,
                    status=LicensedOddsAcquisitionStatus.DENIED,
                    reason_code="authorization_denied",
                ),
            )
        if not _credential_present(self._settings):
            return LicensedOddsAcquisition(
                records=(),
                telemetry=_telemetry(
                    scope=normalized_scope,
                    status=LicensedOddsAcquisitionStatus.DENIED,
                    reason_code="credentials_unavailable",
                ),
            )

        quota = source.quota_policy
        # The approved Sportmonks source presently declares only an RPM cap.
        # Refuse a future policy shape rather than silently under-enforcing it.
        if quota.requests_per_day is not None:
            return LicensedOddsAcquisition(
                records=(),
                telemetry=_telemetry(
                    scope=normalized_scope,
                    status=LicensedOddsAcquisitionStatus.DENIED,
                    reason_code="unsupported_quota_policy",
                ),
            )
        if session.in_transaction() or session.new or session.dirty or session.deleted:
            raise ValueError("licensed odds acquisition requires a clean dedicated session")
        # Recover ambiguous crashed calls in their own short transaction.  A
        # denial caused by the resulting circuit must not roll this evidence
        # back.
        await reap_expired_provider_reservations(
            session,
            now=datetime.now(UTC),
            circuit_cooldown_seconds=self._circuit_open_seconds,
        )
        await session.commit()
        admitted_at = datetime.now(UTC)
        try:
            await configure_provider_quota(
                session,
                adapter_key=SPORTMONKS_ADAPTER_KEY,
                source_key=SPORTMONKS_SOURCE_KEY,
                quota_limit=quota.requests_per_minute,
                quota_window_seconds=60 if quota.requests_per_minute is not None else None,
                now=admitted_at,
            )
            reservation = await reserve_provider_quota(
                session,
                adapter_key=SPORTMONKS_ADAPTER_KEY,
                source_key=SPORTMONKS_SOURCE_KEY,
                reservation_key=_reservation_key(
                    scope=normalized_scope,
                    job_id=job_id,
                    run_id=run_id,
                    correlation_id=correlation_id,
                ),
                task_run_id=run_id,
                execution_token=execution_token,
                reservation_ttl_seconds=max(60, int(self._settings.sportmonks_timeout_seconds) + 60),
                now=admitted_at,
            )
        except (ProviderRuntimeUnavailableError, ValueError) as exc:
            await session.rollback()
            reason_code = getattr(exc, "reason_code", "quota_or_circuit_denied")
            return LicensedOddsAcquisition(
                records=(),
                telemetry=_telemetry(
                    scope=normalized_scope,
                    status=LicensedOddsAcquisitionStatus.DENIED,
                    reason_code=reason_code,
                ),
            )
        await session.commit()  # durable admission; no row lock crosses egress
        if not reservation.created:
            observation_ids = await self._staged_observation_ids(
                session,
                provider_run_id=run_id,
                correlation_id=correlation_id,
                scheduled_job_run_id=scheduled_job_run_id,
            )
            if observation_ids and reservation.status in {"reserved", "charged", "uncertain"}:
                if reservation.status == "reserved":
                    try:
                        await reconcile_provider_reservation(
                            session,
                            reservation,
                            charged=True,
                            now=datetime.now(UTC),
                        )
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        return LicensedOddsAcquisition(
                            records=(),
                            telemetry=_telemetry(
                                scope=normalized_scope,
                                status=LicensedOddsAcquisitionStatus.FAILED,
                                reason_code="reconciliation_deferred",
                                failure=True,
                            ),
                            observation_ids=observation_ids,
                            replayed=True,
                        )
                else:
                    await session.rollback()
                return LicensedOddsAcquisition(
                    records=(),
                    telemetry=_telemetry(
                        scope=normalized_scope,
                        status=LicensedOddsAcquisitionStatus.ACQUIRED,
                        reason_code="staged_observations_replayed",
                        charged=True,
                        record_count=len(observation_ids),
                    ),
                    observation_ids=observation_ids,
                    replayed=True,
                )
            await session.rollback()
            return LicensedOddsAcquisition(
                records=(),
                telemetry=_telemetry(
                    scope=normalized_scope,
                    status=LicensedOddsAcquisitionStatus.DENIED,
                    reason_code="duplicate_acquisition",
                ),
            )

        try:
            records = await self._adapter.fetch_latest_odds(
                scope=normalized_scope,
                job_id=job_id,
                run_id=run_id,
                correlation_id=correlation_id,
                context=context,
                observed_at=observed_at,
            )
        except Exception as exc:
            # The request might have reached the provider before a transport,
            # validation, or implementation failure. Account conservatively and
            # never surface exception text because HTTP clients may retain URLs.
            failed_at = datetime.now(UTC)
            try:
                await reconcile_provider_reservation(
                    session,
                    reservation,
                    charged=True,
                    failure=True,
                    circuit_open_until=failed_at + timedelta(seconds=self._circuit_open_seconds),
                    now=failed_at,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                return LicensedOddsAcquisition(
                    records=(),
                    telemetry=_telemetry(
                        scope=normalized_scope,
                        status=LicensedOddsAcquisitionStatus.FAILED,
                        reason_code="reconciliation_deferred",
                        failure=True,
                    ),
                )
            return LicensedOddsAcquisition(
                records=(),
                telemetry=_telemetry(
                    scope=normalized_scope,
                    status=LicensedOddsAcquisitionStatus.FAILED,
                    reason_code=(
                        exc.reason_code if isinstance(exc, SportmonksOddsAdapterError) else "upstream_request_failed"
                    ),
                    charged=True,
                    failure=True,
                ),
            )

        observation_ids: tuple[int, ...] = ()
        if records:
            staged: list[int] = []
            try:
                for envelope in records:
                    observation = await persist_provider_envelope(
                        session,
                        envelope,
                        context=context,
                        source_descriptor=source,
                        registry=self._registry,
                        scheduled_job_run_id=scheduled_job_run_id,
                    )
                    observation_id = getattr(observation, "id", None)
                    if not isinstance(observation_id, int):
                        raise ValueError("licensed odds envelope was not accepted")
                    staged.append(observation_id)
                # The immutable observations are the durable recovery payload.
                # They must become visible before the reservation can become
                # terminally charged.
                await session.commit()
            except Exception:
                await session.rollback()
                return LicensedOddsAcquisition(
                    records=(),
                    telemetry=_telemetry(
                        scope=normalized_scope,
                        status=LicensedOddsAcquisitionStatus.FAILED,
                        reason_code="observation_staging_deferred",
                        failure=True,
                    ),
                )
            observation_ids = tuple(staged)

        try:
            await reconcile_provider_reservation(
                session,
                reservation,
                charged=True,
                now=datetime.now(UTC),
            )
            await session.commit()
        except Exception:
            await session.rollback()
            return LicensedOddsAcquisition(
                records=(),
                telemetry=_telemetry(
                    scope=normalized_scope,
                    status=LicensedOddsAcquisitionStatus.FAILED,
                    reason_code="reconciliation_deferred",
                    failure=True,
                ),
                observation_ids=observation_ids,
            )
        return LicensedOddsAcquisition(
            records=records,
            telemetry=_telemetry(
                scope=normalized_scope,
                status=LicensedOddsAcquisitionStatus.ACQUIRED,
                reason_code="acquired",
                charged=True,
                record_count=len(records),
            ),
            observation_ids=observation_ids,
        )

    async def _staged_observation_ids(
        self,
        session: AsyncSession,
        *,
        provider_run_id: str,
        correlation_id: str,
        scheduled_job_run_id: int | None,
    ) -> tuple[int, ...]:
        """Find immutable recovery payloads for one durable acquisition."""

        if not hasattr(session, "scalars"):
            return ()
        filters = [
            ProviderObservation.adapter_key == SPORTMONKS_ADAPTER_KEY,
            ProviderObservation.source_key == SPORTMONKS_SOURCE_KEY,
            ProviderObservationReceipt.provider_run_id == provider_run_id,
            ProviderObservationReceipt.correlation_id == correlation_id,
        ]
        if scheduled_job_run_id is not None:
            filters.append(ProviderObservationReceipt.scheduled_job_run_id_snapshot == scheduled_job_run_id)
        ids = (
            await session.scalars(
                select(ProviderObservation.id)
                .join(
                    ProviderObservationReceipt,
                    ProviderObservationReceipt.observation_id == ProviderObservation.id,
                )
                .where(*filters)
                .distinct()
                .order_by(ProviderObservation.id)
            )
        ).all()
        return tuple(ids)
