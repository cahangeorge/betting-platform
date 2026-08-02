"""Transactional quota and circuit controls shared by all provider adapters."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_runtime import ProviderQuotaReservation, ProviderSourceRuntimeState


class ProviderRuntimeUnavailableError(RuntimeError):
    """The provider's circuit or locally known quota rejects a request."""

    def __init__(self, message: str, *, reason_code: str = "provider_runtime_unavailable") -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class QuotaReservation:
    adapter_key: str
    source_key: str
    units: int
    reservation_key: str = ""
    expires_at: datetime | None = None
    created: bool = True
    status: str = "reserved"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _validate_runtime_state(state: ProviderSourceRuntimeState) -> None:
    for field in ("quota_limit", "quota_reserved", "quota_consumed", "provider_remaining", "consecutive_failures"):
        value = getattr(state, field)
        if value is not None and value < 0:
            raise ValueError(f"{field} cannot be negative")
    if state.circuit_state not in {"closed", "open", "half_open"}:
        raise ValueError("invalid circuit_state")
    if state.circuit_open_until is not None:
        _require_aware(state.circuit_open_until, field="circuit_open_until")
    if state.quota_window_seconds is not None and state.quota_window_seconds <= 0:
        raise ValueError("quota_window_seconds must be positive")
    if state.quota_window_started_at is not None:
        _require_aware(state.quota_window_started_at, field="quota_window_started_at")


def _reset_expired_quota_window(state: ProviderSourceRuntimeState, *, now: datetime) -> None:
    """Reset only expired quota accounting, retaining in-flight reservations."""

    if state.quota_window_seconds is None:
        return
    started_at = state.quota_window_started_at
    if started_at is None or now >= started_at + timedelta(seconds=state.quota_window_seconds):
        state.quota_consumed = 0
        # This value belongs to the last upstream response and cannot safely be
        # carried into a new provider window.
        state.provider_remaining = None
        state.quota_window_started_at = now


async def _locked_state(
    session: AsyncSession,
    *,
    adapter_key: str,
    source_key: str,
) -> ProviderSourceRuntimeState:
    """Atomically create (if needed) then lock the one generic source record."""

    bind = session.get_bind()
    dialect = bind.dialect.name
    values = {"adapter_key": adapter_key, "source_key": source_key}
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # supported backends retain correctness with a regular insert.
        from sqlalchemy import insert

    statement = insert(ProviderSourceRuntimeState).values(**values)
    if dialect in {"postgresql", "sqlite"}:
        statement = statement.on_conflict_do_nothing(index_elements=["adapter_key", "source_key"])
    await session.execute(statement)
    result = await session.execute(
        select(ProviderSourceRuntimeState)
        .where(
            ProviderSourceRuntimeState.adapter_key == adapter_key,
            ProviderSourceRuntimeState.source_key == source_key,
        )
        .with_for_update()
    )
    state = result.scalar_one()
    return state


def _available_quota(state: ProviderSourceRuntimeState) -> int | None:
    limits = [limit for limit in (state.quota_limit, state.provider_remaining) if limit is not None]
    if not limits:
        return None
    # ``provider_remaining`` is an upstream value at reconciliation time. It
    # must still account for local outstanding reservations before dispatch.
    if state.provider_remaining is not None:
        upstream_available = state.provider_remaining - state.quota_reserved
        limits.append(upstream_available)
    if state.quota_limit is not None:
        limits.append(state.quota_limit - state.quota_consumed - state.quota_reserved)
    return min(limits)


async def configure_provider_quota(
    session: AsyncSession,
    *,
    adapter_key: str,
    source_key: str,
    quota_limit: int | None,
    quota_window_seconds: int | None,
    now: datetime | None = None,
) -> ProviderSourceRuntimeState:
    """Pin a source's declared local quota without silently resetting usage.

    Configuration is applied under the same row lock as reservations.  A
    changed quota contract while requests are in flight is rejected rather than
    rewriting accounting; rollout configuration must drain first.
    """

    now = _require_aware(now or _utcnow(), field="now")
    if quota_limit is not None and quota_limit < 0:
        raise ValueError("quota_limit cannot be negative")
    if (quota_limit is None) != (quota_window_seconds is None):
        raise ValueError("quota limit and window must be configured together")
    if quota_window_seconds is not None and quota_window_seconds <= 0:
        raise ValueError("quota_window_seconds must be positive")

    state = await _locked_state(session, adapter_key=adapter_key, source_key=source_key)
    _validate_runtime_state(state)
    current = (state.quota_limit, state.quota_window_seconds)
    requested = (quota_limit, quota_window_seconds)
    if current != (None, None) and current != requested:
        if state.quota_reserved:
            raise ProviderRuntimeUnavailableError("provider quota configuration cannot change while reserved")
        raise ProviderRuntimeUnavailableError("provider quota configuration differs from declared source policy")
    if current == (None, None):
        state.quota_limit = quota_limit
        state.quota_window_seconds = quota_window_seconds
        state.quota_window_started_at = now if quota_window_seconds is not None else None
    _reset_expired_quota_window(state, now=now)
    return state


async def reserve_provider_quota(
    session: AsyncSession,
    *,
    adapter_key: str,
    source_key: str,
    units: int = 1,
    reservation_key: str | None = None,
    task_run_id: str | None = None,
    execution_token: str | None = None,
    reservation_ttl_seconds: int = 300,
    now: datetime | None = None,
) -> QuotaReservation:
    """Durably reserve units under lock, then let the caller commit before egress.

    ``reservation_key`` is the acquisition idempotency key.  Retrying a
    committed reserve with the same source, units, and task/execution identity
    returns the original ledger entry without double-counting quota.
    """

    if units < 1:
        raise ValueError("units must be positive")
    if reservation_ttl_seconds <= 0:
        raise ValueError("reservation_ttl_seconds must be positive")
    now = _require_aware(now or _utcnow(), field="now")
    reservation_key = reservation_key or uuid4().hex
    if not reservation_key or len(reservation_key) > 128:
        raise ValueError("reservation_key must be 1..128 characters")
    for field, value in (("task_run_id", task_run_id), ("execution_token", execution_token)):
        if value is not None and (not value or len(value) > 128):
            raise ValueError(f"{field} must be 1..128 characters when provided")

    # Compatibility with the original pure-state helper tests.  Production
    # callers must provide a session so the reservation survives a crash.
    if session is None:
        return await _reserve_legacy_state(
            adapter_key=adapter_key, source_key=source_key, units=units, now=now, reservation_key=reservation_key
        )

    state = await _locked_state(session, adapter_key=adapter_key, source_key=source_key)
    _validate_runtime_state(state)
    existing = await _locked_reservation(session, reservation_key=reservation_key)
    if existing is not None:
        _assert_reservation_identity(
            existing,
            adapter_key=adapter_key,
            source_key=source_key,
            units=units,
            task_run_id=task_run_id,
            execution_token=execution_token,
        )
        return _reservation_value(existing, created=False)

    _reset_expired_quota_window(state, now=now)
    if state.circuit_state == "open":
        if state.circuit_open_until is None or state.circuit_open_until > now:
            raise ProviderRuntimeUnavailableError("provider circuit is open", reason_code="transient_circuit_open")
        state.circuit_state = "half_open"
    if state.circuit_state == "half_open" and state.quota_reserved:
        raise ProviderRuntimeUnavailableError(
            "provider half-open probe already reserved", reason_code="transient_circuit_open"
        )
    available = _available_quota(state)
    if available is not None and available < units:
        raise ProviderRuntimeUnavailableError("provider quota exhausted", reason_code="quota_exhausted")
    state.quota_reserved += units
    expires_at = now + timedelta(seconds=reservation_ttl_seconds)
    record = ProviderQuotaReservation(
        runtime_state_id=state.id,
        reservation_key=reservation_key,
        adapter_key=adapter_key,
        source_key=source_key,
        task_run_id=task_run_id,
        execution_token=execution_token,
        units=units,
        status="reserved",
        quota_window_started_at=state.quota_window_started_at,
        reserved_at=now,
        expires_at=expires_at,
    )
    session.add(record)
    # Flush now to make the unique acquisition key race explicit inside this
    # transaction, rather than discovering it after the adapter can egress.
    await session.flush()
    return _reservation_value(record, created=True)


async def reconcile_provider_reservation(
    session: AsyncSession,
    reservation: QuotaReservation,
    *,
    charged: bool,
    provider_remaining: int | None = None,
    failure: bool = False,
    circuit_open_until: datetime | None = None,
    now: datetime | None = None,
) -> ProviderSourceRuntimeState:
    """CAS-reconcile a durable reservation exactly once.

    Same-outcome terminal replays are harmless; a different outcome never
    mutates accounting.  The aggregate runtime row is locked before the ledger
    row, matching reservation/reaper lock ordering.
    """

    now = _require_aware(now or _utcnow(), field="now")
    if provider_remaining is not None and provider_remaining < 0:
        raise ValueError("provider_remaining cannot be negative")
    if circuit_open_until is not None:
        _require_aware(circuit_open_until, field="circuit_open_until")
        if circuit_open_until <= now:
            raise ValueError("circuit_open_until must be in the future")
    if session is None:
        return await _reconcile_legacy_state(
            reservation,
            charged=charged,
            provider_remaining=provider_remaining,
            failure=failure,
            circuit_open_until=circuit_open_until,
            now=now,
        )
    # Reject an accidental cross-source reconciliation before lazily creating
    # a runtime state for that unrelated source.  The later locked lookup is
    # still authoritative for CAS semantics.
    preflight = await session.scalar(
        select(ProviderQuotaReservation).where(ProviderQuotaReservation.reservation_key == reservation.reservation_key)
    )
    if preflight is not None:
        _assert_reservation_identity(
            preflight,
            adapter_key=reservation.adapter_key,
            source_key=reservation.source_key,
            units=reservation.units,
        )
    state = await _locked_state(
        session,
        adapter_key=reservation.adapter_key,
        source_key=reservation.source_key,
    )
    _validate_runtime_state(state)
    _reset_expired_quota_window(state, now=now)
    record = await _locked_reservation(session, reservation_key=reservation.reservation_key)
    if record is None:
        raise ProviderRuntimeUnavailableError("reservation is invalid")
    _assert_reservation_identity(
        record,
        adapter_key=reservation.adapter_key,
        source_key=reservation.source_key,
        units=reservation.units,
    )
    desired_status = "charged" if charged else "released"
    if record.status != "reserved":
        if record.status == desired_status or (record.status == "uncertain" and charged):
            return state
        raise ProviderRuntimeUnavailableError("reservation was already reconciled with a different outcome")
    if state.quota_reserved < record.units:
        raise ProviderRuntimeUnavailableError("reservation accounting is inconsistent")
    state.quota_reserved -= record.units
    if charged:
        state.quota_consumed += record.units
    if provider_remaining is not None:
        state.provider_remaining = provider_remaining
    state.last_reconciled_at = now
    if failure:
        state.consecutive_failures += 1
        state.last_error_at = now
        if circuit_open_until is not None:
            state.circuit_state = "open"
            state.circuit_open_until = circuit_open_until
    else:
        state.consecutive_failures = 0
        state.circuit_state = "closed"
        state.circuit_open_until = None
    record.status = desired_status
    record.reconciled_at = now
    return state


async def reap_expired_provider_reservations(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    circuit_cooldown_seconds: int = 60,
) -> int:
    """Conservatively settle crashed, pre-egress reservations as uncertain.

    We cannot prove the upstream was not contacted after a process crash, so an
    expired reservation is charged and opens its source circuit.  A scheduled
    worker can call this in a short transaction before admitting more work.
    """

    if circuit_cooldown_seconds <= 0:
        raise ValueError("circuit_cooldown_seconds must be positive")
    now = _require_aware(now or _utcnow(), field="now")
    expired_state_ids = select(ProviderQuotaReservation.runtime_state_id).where(
        ProviderQuotaReservation.status == "reserved",
        ProviderQuotaReservation.expires_at <= now,
    )
    state_query: Select[tuple[ProviderSourceRuntimeState]] = (
        select(ProviderSourceRuntimeState)
        .where(ProviderSourceRuntimeState.id.in_(expired_state_ids))
        .with_for_update(skip_locked=True)
    )
    states = (await session.execute(state_query)).scalars().all()
    reaped = 0
    for state in states:
        _validate_runtime_state(state)
        _reset_expired_quota_window(state, now=now)
        records = (
            (
                await session.execute(
                    select(ProviderQuotaReservation)
                    .where(
                        ProviderQuotaReservation.runtime_state_id == state.id,
                        ProviderQuotaReservation.status == "reserved",
                        ProviderQuotaReservation.expires_at <= now,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        for record in records:
            if state.quota_reserved < record.units:
                raise ProviderRuntimeUnavailableError("reservation accounting is inconsistent")
            state.quota_reserved -= record.units
            state.quota_consumed += record.units
            record.status = "uncertain"
            record.reconciled_at = now
            reaped += 1
        if records:
            state.consecutive_failures += len(records)
            state.last_error_at = now
            state.circuit_state = "open"
            state.circuit_open_until = now + timedelta(seconds=circuit_cooldown_seconds)
            state.last_reconciled_at = now
    return reaped


async def _locked_reservation(session: AsyncSession, *, reservation_key: str) -> ProviderQuotaReservation | None:
    return await session.scalar(
        select(ProviderQuotaReservation)
        .where(ProviderQuotaReservation.reservation_key == reservation_key)
        .with_for_update()
    )


def _assert_reservation_identity(
    record: ProviderQuotaReservation,
    *,
    adapter_key: str,
    source_key: str,
    units: int,
    task_run_id: str | None = None,
    execution_token: str | None = None,
) -> None:
    if (record.adapter_key, record.source_key, record.units) != (adapter_key, source_key, units):
        raise ProviderRuntimeUnavailableError("reservation key belongs to a different provider acquisition")
    if task_run_id is not None and record.task_run_id != task_run_id:
        raise ProviderRuntimeUnavailableError("reservation key belongs to a different task run")
    # A retry is intentionally allowed to carry a new worker fence/execution
    # token.  The durable acquisition key is the idempotency boundary; the
    # original token remains immutable audit evidence on the reservation.


def _reservation_value(record: ProviderQuotaReservation, *, created: bool) -> QuotaReservation:
    return QuotaReservation(
        adapter_key=record.adapter_key,
        source_key=record.source_key,
        units=record.units,
        reservation_key=record.reservation_key,
        expires_at=record.expires_at,
        created=created,
        status=record.status,
    )


async def _reserve_legacy_state(**kwargs) -> QuotaReservation:
    """Retain the old no-session behavior only for existing unit-test callers."""
    state = await _locked_state(None, adapter_key=kwargs["adapter_key"], source_key=kwargs["source_key"])
    _validate_runtime_state(state)
    _reset_expired_quota_window(state, now=kwargs["now"])
    if state.circuit_state == "open":
        if state.circuit_open_until is None or state.circuit_open_until > kwargs["now"]:
            raise ProviderRuntimeUnavailableError("provider circuit is open")
        state.circuit_state = "half_open"
    if state.circuit_state == "half_open" and state.quota_reserved:
        raise ProviderRuntimeUnavailableError("provider half-open probe already reserved")
    available = _available_quota(state)
    if available is not None and available < kwargs["units"]:
        raise ProviderRuntimeUnavailableError("provider quota exhausted")
    state.quota_reserved += kwargs["units"]
    return QuotaReservation(
        kwargs["adapter_key"], kwargs["source_key"], kwargs["units"], kwargs["reservation_key"], None, True
    )


async def _reconcile_legacy_state(reservation: QuotaReservation, **kwargs) -> ProviderSourceRuntimeState:
    state = await _locked_state(None, adapter_key=reservation.adapter_key, source_key=reservation.source_key)
    _validate_runtime_state(state)
    _reset_expired_quota_window(state, now=kwargs["now"])
    if state.quota_reserved < reservation.units:
        raise ProviderRuntimeUnavailableError("reservation was already reconciled or is invalid")
    state.quota_reserved -= reservation.units
    if kwargs["charged"]:
        state.quota_consumed += reservation.units
    if kwargs["provider_remaining"] is not None:
        state.provider_remaining = kwargs["provider_remaining"]
    state.last_reconciled_at = kwargs["now"]
    if kwargs["failure"]:
        state.consecutive_failures += 1
        state.last_error_at = kwargs["now"]
        if kwargs["circuit_open_until"] is not None:
            state.circuit_state = "open"
            state.circuit_open_until = kwargs["circuit_open_until"]
    else:
        state.consecutive_failures = 0
        state.circuit_state = "closed"
        state.circuit_open_until = None
    return state
