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
    ProviderPolicyError,
    ProviderQuotaPolicy,
    ProviderRegistry,
    ProviderSourceDescriptor,
    ProviderTransport,
    SportmonksOddsAdapter,
    SportmonksOddsAdapterError,
)
from app.providers.sportmonks_odds import MAX_RESPONSE_BYTES

SENTINEL = "sportmonks-token-sentinel"


def _registry(*, policy=ProductionPolicy.ALLOWED) -> ProviderRegistry:
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


def _response(request: httpx.Request) -> httpx.Response:
    assert request.url.scheme == "https"
    assert request.url.host == "api.sportmonks.com"
    assert request.url.path == "/v3/football/odds/pre-match/latest"
    assert request.url.params["api_token"] == SENTINEL
    return httpx.Response(
        200,
        json={
            "data": [
                {
                    "id": 19,
                    "fixture_id": 42,
                    "label": "Home",
                    "value": "2.15",
                    "updated_at": "2026-08-01T12:00:00Z",
                    "fixture": {
                        "id": 42,
                        "starting_at": "2026-08-02T12:00:00Z",
                        "league": {"id": 8},
                        "participants": [
                            {"name": "Home FC", "meta": {"location": "home"}},
                            {"name": "Away FC", "meta": {"location": "away"}},
                        ],
                    },
                    "bookmaker": {"id": 7, "name": "Bookmaker"},
                    "market": {"id": 1, "name": "Match Winner"},
                }
            ]
        },
        request=request,
    )


@pytest.mark.asyncio
async def test_adapter_maps_bounded_v3_response_to_strict_odds_envelope() -> None:
    adapter = SportmonksOddsAdapter(
        Settings(_env_file=None, sportmonks_api_token=SENTINEL),
        registry=_registry(),
        transport=httpx.MockTransport(_response),
    )

    records = await adapter.fetch_latest_odds(
        scope="prematch",
        job_id="job-1",
        run_id="run-1",
        correlation_id="corr-1",
        context=ProviderExecutionContext.TEST,
        observed_at=datetime(2026, 8, 1, 12, 1, tzinfo=UTC),
    )

    assert len(records) == 1
    record = records[0]
    assert (record.adapter_key, record.source_key, record.capability, record.source_id) == (
        "sportmonks-v3-odds",
        "sportmonks-football-v3-standard-odds",
        ProviderCapability.ODDS,
        "42",
    )
    assert record.payload["competition_key"] == "8"
    assert record.payload["quotes"][0]["price"] == "2.15"
    assert SENTINEL not in record.payload_json


@pytest.mark.asyncio
async def test_adapter_policy_gate_prevents_any_network_call_and_redacts_token(caplog) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _response(request)

    adapter = SportmonksOddsAdapter(
        Settings(_env_file=None, sportmonks_api_token=SENTINEL),
        registry=_registry(policy=ProductionPolicy.APPROVAL_REQUIRED),
        transport=httpx.MockTransport(handler),
    )
    with caplog.at_level("INFO"):
        with pytest.raises(ProviderPolicyError) as raised:
            await adapter.fetch_latest_odds(scope="inplay", job_id="job", run_id="run", correlation_id="corr")
    assert not called
    assert SENTINEL not in str(raised.value)
    assert SENTINEL not in caplog.text


@pytest.mark.asyncio
async def test_adapter_missing_credential_prevents_any_network_call_and_redacts_inputs(caplog) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _response(request)

    adapter = SportmonksOddsAdapter(
        Settings(_env_file=None), registry=_registry(), transport=httpx.MockTransport(handler)
    )
    with caplog.at_level("INFO"):
        with pytest.raises(SportmonksOddsAdapterError) as raised:
            await adapter.fetch_latest_odds(scope="prematch", job_id="job", run_id="run", correlation_id="corr")
    assert not called
    assert SENTINEL not in str(raised.value)
    assert SENTINEL not in caplog.text


@pytest.mark.asyncio
async def test_adapter_auth_transport_keeps_token_out_of_httpx_logs_and_errors(caplog) -> None:
    transported_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        transported_urls.append(str(request.url))
        assert request.url.params["api_token"] == SENTINEL
        return httpx.Response(401, request=request)

    adapter = SportmonksOddsAdapter(
        Settings(_env_file=None, sportmonks_api_token=SENTINEL),
        registry=_registry(),
        transport=httpx.MockTransport(handler),
    )
    with caplog.at_level("INFO", logger="httpx"):
        with pytest.raises(SportmonksOddsAdapterError) as raised:
            await adapter.fetch_latest_odds(scope="inplay", job_id="job", run_id="run", correlation_id="corr")

    assert len(transported_urls) == 1
    assert SENTINEL in transported_urls[0]
    assert str(raised.value) == "Sportmonks odds request failed"
    assert raised.value.reason_code == "upstream_http_error"
    assert raised.value.__cause__ is None
    assert SENTINEL not in str(raised.value)
    assert SENTINEL not in caplog.text
    assert "api_token=" not in caplog.text
    assert "api.sportmonks.com" not in str(raised.value)


@pytest.mark.asyncio
async def test_adapter_classifies_upstream_5xx_without_exposing_request_url() -> None:
    adapter = SportmonksOddsAdapter(
        Settings(_env_file=None, sportmonks_api_token=SENTINEL),
        registry=_registry(),
        transport=httpx.MockTransport(lambda request: httpx.Response(503, request=request)),
    )

    with pytest.raises(SportmonksOddsAdapterError) as raised:
        await adapter.fetch_latest_odds(scope="prematch", job_id="job", run_id="run", correlation_id="corr")

    assert raised.value.reason_code == "upstream_5xx"
    assert SENTINEL not in str(raised.value)


@pytest.mark.asyncio
async def test_adapter_classifies_provider_429_as_quota_exhausted() -> None:
    adapter = SportmonksOddsAdapter(
        Settings(_env_file=None, sportmonks_api_token=SENTINEL),
        registry=_registry(),
        transport=httpx.MockTransport(lambda request: httpx.Response(429, request=request)),
    )

    with pytest.raises(SportmonksOddsAdapterError) as raised:
        await adapter.fetch_latest_odds(scope="prematch", job_id="job", run_id="run", correlation_id="corr")

    assert raised.value.reason_code == "quota_exhausted"


@pytest.mark.asyncio
async def test_adapter_rejects_declared_oversize_response_before_reading_body() -> None:
    class NeverRead(httpx.AsyncByteStream):
        iterated = False

        async def __aiter__(self):
            self.iterated = True
            yield b"{}"

    body = NeverRead()
    adapter = SportmonksOddsAdapter(
        Settings(_env_file=None, sportmonks_api_token=SENTINEL),
        registry=_registry(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-length": str(MAX_RESPONSE_BYTES + 1)},
                stream=body,
                request=request,
            )
        ),
    )

    with pytest.raises(SportmonksOddsAdapterError, match="byte limit"):
        await adapter.fetch_latest_odds(scope="prematch", job_id="job", run_id="run", correlation_id="corr")

    assert body.iterated is False


@pytest.mark.asyncio
async def test_adapter_incrementally_caps_chunked_response(monkeypatch) -> None:
    import app.providers.sportmonks_odds as sportmonks_odds

    class Chunked(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"123"
            yield b"45"
            raise AssertionError("reader must stop as soon as the cap is exceeded")

    monkeypatch.setattr(sportmonks_odds, "MAX_RESPONSE_BYTES", 4)
    adapter = SportmonksOddsAdapter(
        Settings(_env_file=None, sportmonks_api_token=SENTINEL),
        registry=_registry(),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Chunked(), request=request)),
    )

    with pytest.raises(SportmonksOddsAdapterError, match="byte limit"):
        await adapter.fetch_latest_odds(scope="prematch", job_id="job", run_id="run", correlation_id="corr")
