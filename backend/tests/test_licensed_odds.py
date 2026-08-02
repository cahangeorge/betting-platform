from datetime import UTC, datetime

import httpx
import pytest

from app.config import Settings
from app.providers import (
    ProductionPolicy,
    ProviderCapability,
    ProviderDescriptor,
    ProviderExecutionContext,
    ProviderFreshnessPolicy,
    ProviderKind,
    ProviderQuotaPolicy,
    ProviderRegistry,
    ProviderSourceDescriptor,
    ProviderTransport,
)
from app.providers.sportmonks_odds import SportmonksOddsAdapterError
from app.services.licensed_odds import LicensedOddsAcquisitionStatus, LicensedOddsService
from app.services.provider_runtime import ProviderRuntimeUnavailableError, QuotaReservation

SENTINEL = "licensed-odds-token-sentinel"


class _FakeSession:
    def __init__(self):
        self.new = set()
        self.dirty = set()
        self.deleted = set()
        self.commits = 0
        self.rollbacks = 0

    def in_transaction(self):
        return False

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.fixture(autouse=True)
def _stub_expired_reservation_reaper(monkeypatch):
    async def reap(*_args, **_kwargs):
        return 0

    monkeypatch.setattr("app.services.licensed_odds.reap_expired_provider_reservations", reap)


def _registry(*, policy: ProductionPolicy = ProductionPolicy.ALLOWED) -> ProviderRegistry:
    adapter = ProviderDescriptor(
        key="sportmonks-v3-odds",
        display_name="Sportmonks",
        kind=ProviderKind.ODDS,
        transport=ProviderTransport.API,
        capabilities=frozenset({ProviderCapability.ODDS}),
        production_policy=policy,
        policy_reason="approval required" if policy is not ProductionPolicy.ALLOWED else "",
    )
    source = ProviderSourceDescriptor(
        adapter_key="sportmonks-v3-odds",
        source_key="sportmonks-football-v3-standard-odds",
        capabilities=frozenset({ProviderCapability.ODDS}),
        production_policy=policy,
        policy_reason="approval required" if policy is not ProductionPolicy.ALLOWED else "",
        quota_policy=ProviderQuotaPolicy(requests_per_minute=60),
        freshness_policy=ProviderFreshnessPolicy(max_age_seconds=300),
    )
    return ProviderRegistry(
        (adapter,),
        (source,),
        operation_capabilities={
            ("sportmonks-v3-odds", "sportmonks-football-v3-standard-odds", "fetch_latest_odds"): ProviderCapability.ODDS
        },
    )


class _FakeAdapter:
    def __init__(self, result=()):
        self.called = 0
        self.result = result

    async def fetch_latest_odds(self, **_kwargs):
        self.called += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.asyncio
async def test_duplicate_durable_acquisition_never_repeats_egress(monkeypatch) -> None:
    adapter = _FakeAdapter()
    existing = QuotaReservation(
        "sportmonks-v3-odds",
        "sportmonks-football-v3-standard-odds",
        1,
        reservation_key="a" * 64,
        created=False,
    )

    async def configure(*_args, **_kwargs):
        return None

    async def reserve(*_args, **_kwargs):
        return existing

    monkeypatch.setattr("app.services.licensed_odds.configure_provider_quota", configure)
    monkeypatch.setattr("app.services.licensed_odds.reserve_provider_quota", reserve)
    session = _FakeSession()
    outcome = await LicensedOddsService(
        Settings(_env_file=None, sportmonks_api_token=SENTINEL), registry=_registry(), adapter=adapter
    ).acquire_sportmonks_latest(
        session,
        scope="prematch",
        job_id="job",
        run_id="run",
        correlation_id="corr",
    )

    assert adapter.called == 0
    assert session.commits == 2
    assert outcome.telemetry.reason_code == "duplicate_acquisition"


@pytest.mark.asyncio
async def test_authorization_denial_has_zero_transport_requests() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": []})

    service = LicensedOddsService(
        Settings(_env_file=None, sportmonks_api_token=SENTINEL),
        registry=_registry(policy=ProductionPolicy.APPROVAL_REQUIRED),
        transport=httpx.MockTransport(handler),
    )
    outcome = await service.acquire_sportmonks_latest(
        _FakeSession(), scope="prematch", job_id="job", run_id="run", correlation_id="corr"
    )
    assert calls == 0
    assert outcome.records == ()
    assert outcome.telemetry.status is LicensedOddsAcquisitionStatus.DENIED
    assert outcome.telemetry.reason_code == "authorization_denied"


@pytest.mark.asyncio
async def test_missing_credential_has_zero_transport_requests() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": []})

    service = LicensedOddsService(
        Settings(_env_file=None), registry=_registry(), transport=httpx.MockTransport(handler)
    )
    outcome = await service.acquire_sportmonks_latest(
        object(), scope="prematch", job_id="job", run_id="run", correlation_id="corr"
    )
    assert calls == 0
    assert outcome.telemetry.reason_code == "credentials_unavailable"


@pytest.mark.asyncio
async def test_quota_or_circuit_denial_has_zero_adapter_requests(monkeypatch) -> None:
    adapter = _FakeAdapter()

    async def configure(*_args, **_kwargs):
        return None

    async def reserve(*_args, **_kwargs):
        raise ProviderRuntimeUnavailableError("provider quota exhausted", reason_code="quota_exhausted")

    monkeypatch.setattr("app.services.licensed_odds.configure_provider_quota", configure)
    monkeypatch.setattr("app.services.licensed_odds.reserve_provider_quota", reserve)
    service = LicensedOddsService(
        Settings(_env_file=None, sportmonks_api_token=SENTINEL), registry=_registry(), adapter=adapter
    )
    outcome = await service.acquire_sportmonks_latest(
        _FakeSession(), scope="prematch", job_id="job", run_id="run", correlation_id="corr"
    )
    assert adapter.called == 0
    assert outcome.telemetry.reason_code == "quota_exhausted"


@pytest.mark.asyncio
async def test_acquisition_configures_source_quota_then_reconciles_success(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []
    adapter = _FakeAdapter()
    reservation = QuotaReservation("sportmonks-v3-odds", "sportmonks-football-v3-standard-odds", 1)

    async def configure(*_args, **kwargs):
        calls.append(("configure", kwargs))

    async def reserve(*_args, **kwargs):
        calls.append(("reserve", kwargs))
        return reservation

    async def reconcile(*_args, **kwargs):
        calls.append(("reconcile", kwargs))

    monkeypatch.setattr("app.services.licensed_odds.configure_provider_quota", configure)
    monkeypatch.setattr("app.services.licensed_odds.reserve_provider_quota", reserve)
    monkeypatch.setattr("app.services.licensed_odds.reconcile_provider_reservation", reconcile)
    service = LicensedOddsService(
        Settings(_env_file=None, sportmonks_api_token=SENTINEL), registry=_registry(), adapter=adapter
    )
    session = _FakeSession()
    outcome = await service.acquire_sportmonks_latest(
        session,
        scope="PREMATCH",
        job_id="job",
        run_id="run",
        correlation_id="corr",
        context=ProviderExecutionContext.TEST,
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert [name for name, _ in calls] == ["configure", "reserve", "reconcile"]
    assert calls[0][1]["quota_limit"] == 60
    assert calls[0][1]["quota_window_seconds"] == 60
    assert len(calls[1][1]["reservation_key"]) == 64
    assert calls[1][1]["task_run_id"] == "run"
    assert calls[2][1] == {"charged": True, "now": calls[2][1]["now"]}
    assert adapter.called == 1
    assert session.commits == 3
    assert outcome.telemetry.status is LicensedOddsAcquisitionStatus.ACQUIRED
    assert outcome.telemetry.charged is True


@pytest.mark.asyncio
async def test_upstream_failure_is_conservatively_charged_and_opens_circuit(monkeypatch) -> None:
    calls: list[dict] = []
    adapter = _FakeAdapter(SportmonksOddsAdapterError("safe failure"))
    reservation = QuotaReservation("sportmonks-v3-odds", "sportmonks-football-v3-standard-odds", 1)

    async def configure(*_args, **_kwargs):
        return None

    async def reserve(*_args, **_kwargs):
        return reservation

    async def reconcile(*_args, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("app.services.licensed_odds.configure_provider_quota", configure)
    monkeypatch.setattr("app.services.licensed_odds.reserve_provider_quota", reserve)
    monkeypatch.setattr("app.services.licensed_odds.reconcile_provider_reservation", reconcile)
    service = LicensedOddsService(
        Settings(_env_file=None, sportmonks_api_token=SENTINEL), registry=_registry(), adapter=adapter
    )
    session = _FakeSession()
    outcome = await service.acquire_sportmonks_latest(
        session, scope="inplay", job_id="job", run_id="run", correlation_id="corr"
    )
    assert adapter.called == 1
    assert calls[0]["charged"] is True
    assert calls[0]["failure"] is True
    assert calls[0]["circuit_open_until"] > calls[0]["now"]
    assert outcome.telemetry.status is LicensedOddsAcquisitionStatus.FAILED
    assert outcome.telemetry.failure is True
    assert session.commits == 3


@pytest.mark.asyncio
async def test_runtime_quota_configuration_is_pinned_under_the_state_lock(monkeypatch) -> None:
    from app.models import ProviderSourceRuntimeState
    from app.services.provider_runtime import configure_provider_quota

    state = ProviderSourceRuntimeState(
        adapter_key="sportmonks-v3-odds",
        source_key="sportmonks-football-v3-standard-odds",
        quota_reserved=0,
        quota_consumed=0,
        consecutive_failures=0,
        circuit_state="closed",
    )

    async def locked_state(*_args, **_kwargs):
        return state

    monkeypatch.setattr("app.services.provider_runtime._locked_state", locked_state)
    now = datetime(2026, 8, 1, tzinfo=UTC)
    await configure_provider_quota(
        None,
        adapter_key=state.adapter_key,
        source_key=state.source_key,
        quota_limit=60,
        quota_window_seconds=60,
        now=now,
    )
    assert (state.quota_limit, state.quota_window_seconds, state.quota_window_started_at) == (60, 60, now)
    with pytest.raises(ProviderRuntimeUnavailableError, match="differs"):
        await configure_provider_quota(
            None,
            adapter_key=state.adapter_key,
            source_key=state.source_key,
            quota_limit=30,
            quota_window_seconds=60,
            now=now,
        )
