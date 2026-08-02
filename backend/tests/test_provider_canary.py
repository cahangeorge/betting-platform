import pytest

from app.diagnostics import provider_canary
from app.providers import ProviderExecutionContext


@pytest.mark.asyncio
async def test_penaltyblog_goal_expectancy_canary_authorizes_before_unchanged_bridge_call(monkeypatch):
    calls: list[object] = []
    payload = {
        "operation": "goal_expectancy",
        "payload": {
            "home": 0.48,
            "draw": 0.28,
            "away": 0.24,
            "return_details": True,
        },
    }

    class Registry:
        def require_operation(self, adapter_key, source_key, operation, *, context):
            calls.append(("policy", adapter_key, source_key, operation, context))
            assert (adapter_key, source_key, operation, context) == (
                "penaltyblog",
                "local-model",
                "goal_expectancy",
                ProviderExecutionContext.CANARY,
            )

    async def fake_penaltyblog(actual_payload):
        calls.append(("bridge", actual_payload))
        return {"operation": "goal_expectancy", "result": {"home_goals": 1.2}}

    async def fake_soccerdata(_payload):
        return {"groups": []}

    async def fake_oddsharvester_browser():
        return None

    monkeypatch.setattr(provider_canary.settings, "bridge_validation_issues", lambda: calls.append(("runtime",)) or [])
    monkeypatch.setattr(provider_canary, "DEFAULT_PROVIDER_REGISTRY", Registry())
    monkeypatch.setattr(provider_canary, "run_penaltyblog", fake_penaltyblog)
    monkeypatch.setattr(provider_canary, "run_soccerdata", fake_soccerdata)
    monkeypatch.setattr(provider_canary, "_verify_oddsharvester_browser", fake_oddsharvester_browser)

    await provider_canary.verify_provider_runtime()

    assert calls == [
        ("policy", "penaltyblog", "local-model", "goal_expectancy", ProviderExecutionContext.CANARY),
        ("runtime",),
        ("bridge", payload),
    ]


@pytest.mark.asyncio
async def test_penaltyblog_goal_expectancy_canary_does_not_call_bridge_when_policy_rejects(monkeypatch):
    bridge_called = False

    class RejectingRegistry:
        def require_operation(self, adapter_key, source_key, operation, *, context):
            raise PermissionError("policy rejected")

    async def fake_penaltyblog(_payload):
        nonlocal bridge_called
        bridge_called = True
        return {"operation": "goal_expectancy"}

    monkeypatch.setattr(provider_canary.settings, "bridge_validation_issues", lambda: [])
    monkeypatch.setattr(provider_canary, "DEFAULT_PROVIDER_REGISTRY", RejectingRegistry())
    monkeypatch.setattr(provider_canary, "run_penaltyblog", fake_penaltyblog)

    with pytest.raises(PermissionError, match="policy rejected"):
        await provider_canary.verify_provider_runtime()

    assert bridge_called is False
