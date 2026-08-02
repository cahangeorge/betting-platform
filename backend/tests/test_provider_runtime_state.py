from datetime import UTC, datetime, timedelta

import pytest

from app.models import OddsQuote, OddsSnapshot, ProviderQuotaReservation, ProviderSourceRuntimeState
from app.services.provider_runtime import (
    ProviderRuntimeUnavailableError,
    reconcile_provider_reservation,
    reserve_provider_quota,
)


@pytest.fixture
def state() -> ProviderSourceRuntimeState:
    return ProviderSourceRuntimeState(
        adapter_key="licensed-odds",
        source_key="sandbox",
        quota_reserved=0,
        quota_consumed=0,
        consecutive_failures=0,
        circuit_state="closed",
    )


@pytest.mark.asyncio
async def test_quota_reservation_is_reconciled_once_and_enforces_known_remaining(monkeypatch, state):
    async def locked_state(*_args, **_kwargs):
        return state

    monkeypatch.setattr("app.services.provider_runtime._locked_state", locked_state)
    reservation = await reserve_provider_quota(None, adapter_key="licensed-odds", source_key="sandbox")
    state = await reconcile_provider_reservation(
        None, reservation, charged=True, provider_remaining=0, now=datetime(2026, 8, 1, tzinfo=UTC)
    )
    assert (state.quota_reserved, state.quota_consumed, state.provider_remaining) == (0, 1, 0)

    with pytest.raises(ProviderRuntimeUnavailableError, match="quota exhausted"):
        await reserve_provider_quota(None, adapter_key="licensed-odds", source_key="sandbox")
    with pytest.raises(ProviderRuntimeUnavailableError, match="already reconciled"):
        await reconcile_provider_reservation(None, reservation, charged=True)


@pytest.mark.asyncio
async def test_open_circuit_rejects_until_one_half_open_probe_is_reserved(monkeypatch, state):
    async def locked_state(*_args, **_kwargs):
        return state

    monkeypatch.setattr("app.services.provider_runtime._locked_state", locked_state)
    now = datetime(2026, 8, 1, tzinfo=UTC)
    reservation = await reserve_provider_quota(None, adapter_key="licensed-odds", source_key="sandbox", now=now)
    await reconcile_provider_reservation(
        None,
        reservation,
        charged=False,
        failure=True,
        circuit_open_until=now + timedelta(minutes=1),
        now=now,
    )
    with pytest.raises(ProviderRuntimeUnavailableError, match="circuit is open"):
        await reserve_provider_quota(None, adapter_key="licensed-odds", source_key="sandbox", now=now)

    probe = await reserve_provider_quota(
        None, adapter_key="licensed-odds", source_key="sandbox", now=now + timedelta(minutes=2)
    )
    with pytest.raises(ProviderRuntimeUnavailableError, match="half-open"):
        await reserve_provider_quota(
            None, adapter_key="licensed-odds", source_key="sandbox", now=now + timedelta(minutes=2)
        )
    state = await reconcile_provider_reservation(None, probe, charged=True, now=now + timedelta(minutes=2))
    assert (state.circuit_state, state.consecutive_failures) == ("closed", 0)


@pytest.mark.asyncio
async def test_expired_quota_window_resets_stale_accounting_but_retains_reservations(monkeypatch, state):
    async def locked_state(*_args, **_kwargs):
        return state

    monkeypatch.setattr("app.services.provider_runtime._locked_state", locked_state)
    state.quota_limit = 2
    state.quota_consumed = 2
    state.quota_reserved = 1
    state.provider_remaining = 0
    state.quota_window_started_at = datetime(2026, 8, 1, tzinfo=UTC)
    state.quota_window_seconds = 60
    await reserve_provider_quota(
        None,
        adapter_key="licensed-odds",
        source_key="sandbox",
        now=datetime(2026, 8, 1, 0, 2, tzinfo=UTC),
    )
    assert (state.quota_consumed, state.provider_remaining, state.quota_reserved) == (0, None, 2)


@pytest.mark.asyncio
async def test_runtime_rejects_naive_time_and_invalid_circuit_input(monkeypatch, state):
    async def locked_state(*_args, **_kwargs):
        return state

    monkeypatch.setattr("app.services.provider_runtime._locked_state", locked_state)
    with pytest.raises(ValueError, match="timezone-aware"):
        await reserve_provider_quota(None, adapter_key="licensed-odds", source_key="sandbox", now=datetime(2026, 8, 1))
    reservation = await reserve_provider_quota(None, adapter_key="licensed-odds", source_key="sandbox")
    with pytest.raises(ValueError, match="future"):
        await reconcile_provider_reservation(
            None,
            reservation,
            charged=False,
            circuit_open_until=datetime(2026, 8, 1, tzinfo=UTC),
            now=datetime(2026, 8, 1, tzinfo=UTC),
        )


def test_generic_quote_and_runtime_models_expose_provider_neutral_contracts():
    snapshot = OddsSnapshot.__table__
    assert snapshot.c.provider_observation_id.nullable is True
    assert next(iter(snapshot.c.provider_observation_id.foreign_keys)).ondelete == "RESTRICT"
    assert {"contract_version", "payload_digest", "mapping_version"} <= set(snapshot.c.keys())

    quote = OddsQuote.__table__
    assert quote.c.price.type.precision == quote.c.line.type.precision == 18
    assert quote.c.price.type.scale == quote.c.line.type.scale == 8
    assert {
        "source_quote_id",
        "provider_bookmaker_key",
        "bookmaker_key",
        "provider_market_key",
        "market_key",
        "period_key",
        "line",
        "selection_key",
        "provider_updated_at",
        "status",
    } <= set(quote.c.keys())
    assert quote.c.bookmaker_key.nullable is True
    assert all(
        quote.c[name].nullable is False
        for name in ("source_quote_id", "provider_bookmaker_key", "provider_market_key", "provider_updated_at")
    )
    assert any(constraint.name == "uq_odds_quotes_snapshot_identity" for constraint in quote.constraints)

    runtime = ProviderSourceRuntimeState.__table__
    assert {
        "adapter_key",
        "source_key",
        "quota_reserved",
        "circuit_state",
        "quota_window_started_at",
        "quota_window_seconds",
    } <= set(runtime.c.keys())
    assert any(constraint.name == "uq_provider_source_runtime_state_source" for constraint in runtime.constraints)

    reservation = ProviderQuotaReservation.__table__
    required_reservation_columns = {
        "reservation_key",
        "runtime_state_id",
        "units",
        "status",
        "reserved_at",
        "expires_at",
        "reconciled_at",
    }
    assert required_reservation_columns <= set(reservation.c.keys())
    assert next(iter(reservation.c.runtime_state_id.foreign_keys)).ondelete == "RESTRICT"
    assert any(constraint.name == "uq_provider_quota_reservation_key" for constraint in reservation.constraints)
