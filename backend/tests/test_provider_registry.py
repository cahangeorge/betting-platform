import hashlib
from datetime import datetime, timezone

import pytest

from app.providers import (
    DEFAULT_PROVIDER_REGISTRY,
    ProductionPolicy,
    ProviderCapability,
    ProviderCapabilityError,
    ProviderDescriptor,
    ProviderExecutionContext,
    ProviderFreshnessPolicy,
    ProviderKind,
    ProviderPolicyError,
    ProviderQuotaPolicy,
    ProviderRecordEnvelope,
    ProviderRegistry,
    ProviderSourceDescriptor,
    ProviderTransport,
    UnknownProviderError,
    capability_for_operation,
)


def test_default_registry_describes_current_project_boundaries():
    oddsharvester = DEFAULT_PROVIDER_REGISTRY.get("oddsharvester")
    penaltyblog = DEFAULT_PROVIDER_REGISTRY.get("penaltyblog")
    soccerdata = DEFAULT_PROVIDER_REGISTRY.get("soccerdata")
    flumine = DEFAULT_PROVIDER_REGISTRY.get("flumine")

    assert oddsharvester.kind is ProviderKind.ODDS
    assert oddsharvester.supports(ProviderCapability.ODDS)
    assert oddsharvester.production_policy is ProductionPolicy.APPROVAL_REQUIRED

    assert soccerdata.kind is ProviderKind.DATA
    assert soccerdata.supports(ProviderCapability.STATISTICS)
    assert soccerdata.production_policy is ProductionPolicy.APPROVAL_REQUIRED

    assert penaltyblog.kind is ProviderKind.MODEL
    assert penaltyblog.supports(ProviderCapability.PREDICTIONS)
    assert not penaltyblog.supports(ProviderCapability.ODDS)

    assert flumine.kind is ProviderKind.EXECUTION
    assert flumine.production_policy is ProductionPolicy.DISABLED


def test_registry_rejects_duplicate_provider_keys():
    descriptor = ProviderDescriptor(
        key="example",
        display_name="Example",
        kind=ProviderKind.DATA,
        transport=ProviderTransport.API,
        capabilities=frozenset({ProviderCapability.FIXTURES}),
        production_policy=ProductionPolicy.ALLOWED,
    )

    with pytest.raises(ValueError, match="Duplicate provider key: example"):
        ProviderRegistry((descriptor, descriptor))


def test_descriptor_freezes_a_caller_owned_capability_collection():
    capabilities: frozenset[ProviderCapability] = frozenset({ProviderCapability.FIXTURES})
    descriptor = ProviderDescriptor(
        key="example",
        display_name="Example",
        kind=ProviderKind.DATA,
        transport=ProviderTransport.API,
        capabilities=capabilities,
        production_policy=ProductionPolicy.ALLOWED,
    )
    registry = ProviderRegistry((descriptor,))

    capabilities = capabilities | {ProviderCapability.ODDS}

    assert isinstance(descriptor.capabilities, frozenset)
    with pytest.raises(ProviderCapabilityError, match="example does not provide odds"):
        registry.require_capability("example", ProviderCapability.ODDS)


def test_descriptor_normalizes_raw_enum_values_and_keeps_disabled_policy_closed():
    descriptor = ProviderDescriptor(
        key="example",
        display_name="Example",
        kind="data",  # type: ignore[arg-type]
        transport="api",  # type: ignore[arg-type]
        capabilities={"fixtures"},  # type: ignore[arg-type]
        production_policy="disabled",  # type: ignore[arg-type]
        policy_reason="Disabled test provider.",
    )
    registry = ProviderRegistry((descriptor,))

    assert descriptor.kind is ProviderKind.DATA
    assert descriptor.transport is ProviderTransport.API
    assert descriptor.capabilities == frozenset({ProviderCapability.FIXTURES})
    assert descriptor.production_policy is ProductionPolicy.DISABLED
    with pytest.raises(ProviderPolicyError, match="Disabled test provider"):
        registry.require_capability("example", ProviderCapability.FIXTURES, allow_unapproved=True)


def test_descriptor_rejects_unknown_raw_enum_values():
    with pytest.raises(ValueError, match="invalid enum value"):
        ProviderDescriptor(
            key="example",
            display_name="Example",
            kind=ProviderKind.DATA,
            transport=ProviderTransport.API,
            capabilities=frozenset({ProviderCapability.FIXTURES}),
            production_policy="unknown",  # type: ignore[arg-type]
        )


def test_registry_requires_declared_capability_and_known_provider():
    descriptor = DEFAULT_PROVIDER_REGISTRY.require_capability("penaltyblog", ProviderCapability.PREDICTIONS)
    assert descriptor.key == "penaltyblog"

    with pytest.raises(ProviderCapabilityError, match="penaltyblog does not provide odds"):
        DEFAULT_PROVIDER_REGISTRY.require_capability("penaltyblog", ProviderCapability.ODDS)

    with pytest.raises(UnknownProviderError, match="Unknown provider"):
        DEFAULT_PROVIDER_REGISTRY.get("missing")


@pytest.mark.parametrize(
    "provider_key,capability,message",
    [
        ("oddsharvester", ProviderCapability.ODDS, "explicit upstream approval"),
        ("flumine", ProviderCapability.EXECUTION, "excluded from the public MVP"),
    ],
)
def test_legacy_capability_gate_remains_fail_closed_even_when_allow_unapproved_is_requested(
    provider_key, capability, message
):
    with pytest.raises(ProviderPolicyError, match=message):
        DEFAULT_PROVIDER_REGISTRY.require_capability(provider_key, capability, allow_unapproved=True)


def test_provider_record_envelope_is_canonical_and_digest_stable():
    observed_at = datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc)

    first = ProviderRecordEnvelope.from_payload(
        provider_key="example",
        capability=ProviderCapability.RESULTS,
        source_id="match-42",
        observed_at=observed_at,
        payload={"home": 2, "away": 1},
    )
    second = ProviderRecordEnvelope.from_payload(
        provider_key="example",
        capability=ProviderCapability.RESULTS,
        source_id="match-42",
        observed_at=observed_at,
        payload={"away": 1, "home": 2},
    )

    assert first.payload_json == '{"away":1,"home":2}'
    assert first.payload_digest == second.payload_digest
    assert first.payload == {"away": 1, "home": 2}


def test_provider_record_envelope_requires_aware_observation_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        ProviderRecordEnvelope.from_payload(
            provider_key="example",
            capability=ProviderCapability.RESULTS,
            source_id="match-42",
            observed_at=datetime(2026, 8, 1, 12, 30),
            payload={"home": 2, "away": 1},
        )


@pytest.mark.parametrize(
    ("payload_json", "message"),
    [
        ('{"home": 2, "away": 1}', "canonical representation"),
        ("[]", "JSON object"),
        ("not-json", "valid JSON"),
    ],
)
def test_direct_envelope_construction_rejects_noncanonical_payloads(payload_json, message):
    digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    with pytest.raises(ValueError, match=message):
        ProviderRecordEnvelope(
            provider_key="example",
            capability=ProviderCapability.RESULTS,
            source_id="match-42",
            observed_at=datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc),
            payload_json=payload_json,
            payload_digest=digest,
        )


def test_direct_envelope_construction_rejects_digest_mismatch():
    with pytest.raises(ValueError, match="digest does not match"):
        ProviderRecordEnvelope(
            provider_key="example",
            capability=ProviderCapability.RESULTS,
            source_id="match-42",
            observed_at=datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc),
            payload_json='{"away":1,"home":2}',
            payload_digest="0" * 64,
        )


def test_registry_separates_adapter_and_source_identity():
    local_model = DEFAULT_PROVIDER_REGISTRY.require_operation(
        "penaltyblog",
        "local-model",
        "goal_expectancy",
        context=ProviderExecutionContext.CANARY,
    )

    assert local_model.adapter_key == "penaltyblog"
    assert local_model.source_key == "local-model"
    assert local_model.capabilities == frozenset(
        {ProviderCapability.FEATURES, ProviderCapability.PREDICTIONS, ProviderCapability.BACKTESTS}
    )

    with pytest.raises(UnknownProviderError, match="Unknown provider source"):
        DEFAULT_PROVIDER_REGISTRY.require_operation(
            "penaltyblog",
            "missing-source",
            "goal_expectancy",
            context=ProviderExecutionContext.CANARY,
        )


def test_operation_capability_mapping_rejects_unknown_operations():
    assert capability_for_operation("goal_expectancy") is ProviderCapability.PREDICTIONS

    with pytest.raises(ProviderCapabilityError, match="Unknown provider operation"):
        capability_for_operation("unknown-operation")


@pytest.mark.parametrize(
    "context",
    [
        ProviderExecutionContext.PRODUCTION,
        ProviderExecutionContext.CANARY,
        ProviderExecutionContext.TEST,
    ],
)
def test_allowed_source_is_available_in_each_explicit_execution_context(context):
    descriptor = DEFAULT_PROVIDER_REGISTRY.require_operation(
        "penaltyblog",
        "local-model",
        "goal_expectancy",
        context=context,
    )

    assert descriptor.production_policy is ProductionPolicy.ALLOWED


@pytest.mark.parametrize(
    "policy,context,reason",
    [
        (ProductionPolicy.APPROVAL_REQUIRED, ProviderExecutionContext.PRODUCTION, "requires approval"),
        (ProductionPolicy.APPROVAL_REQUIRED, ProviderExecutionContext.CANARY, "requires approval"),
        (ProductionPolicy.APPROVAL_REQUIRED, ProviderExecutionContext.TEST, "requires approval"),
        (ProductionPolicy.DISABLED, ProviderExecutionContext.PRODUCTION, "disabled by policy"),
        (ProductionPolicy.DISABLED, ProviderExecutionContext.CANARY, "disabled by policy"),
        (ProductionPolicy.DISABLED, ProviderExecutionContext.TEST, "disabled by policy"),
    ],
)
def test_source_policy_is_fail_closed_in_every_execution_context(policy, context, reason):
    adapter = ProviderDescriptor(
        key="example",
        display_name="Example",
        kind=ProviderKind.MODEL,
        transport=ProviderTransport.SUBPROCESS,
        capabilities=frozenset({ProviderCapability.PREDICTIONS}),
        production_policy=ProductionPolicy.ALLOWED,
    )
    source = ProviderSourceDescriptor(
        adapter_key="example",
        source_key="remote-model",
        capabilities=frozenset({ProviderCapability.PREDICTIONS}),
        production_policy=policy,
        policy_reason=reason,
    )
    registry = ProviderRegistry(
        (adapter,),
        (source,),
        operation_capabilities={
            ("example", "remote-model", "goal_expectancy"): ProviderCapability.PREDICTIONS,
        },
    )

    with pytest.raises(ProviderPolicyError, match=reason):
        registry.require_operation("example", "remote-model", "goal_expectancy", context=context)


def test_disabled_adapter_rejects_an_otherwise_allowed_source():
    adapter = ProviderDescriptor(
        key="example",
        display_name="Example",
        kind=ProviderKind.MODEL,
        transport=ProviderTransport.SUBPROCESS,
        capabilities=frozenset({ProviderCapability.PREDICTIONS}),
        production_policy=ProductionPolicy.DISABLED,
        policy_reason="adapter execution is disabled",
    )
    source = ProviderSourceDescriptor(
        adapter_key="example",
        source_key="local-model",
        capabilities=frozenset({ProviderCapability.PREDICTIONS}),
        production_policy=ProductionPolicy.ALLOWED,
    )
    registry = ProviderRegistry(
        (adapter,),
        (source,),
        operation_capabilities={
            ("example", "local-model", "goal_expectancy"): ProviderCapability.PREDICTIONS,
        },
    )

    with pytest.raises(ProviderPolicyError, match="adapter execution is disabled"):
        registry.require_operation("example", "local-model", "goal_expectancy")


def test_source_aware_operation_helper_fails_closed_for_an_unmapped_source():
    with pytest.raises(ProviderCapabilityError, match="Unknown provider operation"):
        capability_for_operation("goal_expectancy", adapter_key="penaltyblog", source_key="missing-source")


@pytest.mark.parametrize(
    "quota_policy,freshness_policy",
    [
        ({"requests_per_minute": -1}, {}),
        ({"requests_per_day": -1}, {}),
        ({}, {"max_age_seconds": -1}),
    ],
)
def test_source_descriptor_rejects_negative_quota_or_freshness_policy(quota_policy, freshness_policy):
    with pytest.raises(ValueError):
        ProviderSourceDescriptor(
            adapter_key="example",
            source_key="local-model",
            capabilities=frozenset({ProviderCapability.PREDICTIONS}),
            production_policy=ProductionPolicy.ALLOWED,
            quota_policy=quota_policy,
            freshness_policy=freshness_policy,
        )


def test_explicit_source_quota_and_freshness_policy_are_preserved():
    descriptor = ProviderSourceDescriptor(
        adapter_key="example",
        source_key="local-model",
        capabilities=frozenset({ProviderCapability.PREDICTIONS}),
        production_policy=ProductionPolicy.ALLOWED,
        quota_policy=ProviderQuotaPolicy(requests_per_minute=30, requests_per_day=1_000),
        freshness_policy=ProviderFreshnessPolicy(max_age_seconds=300),
    )

    assert descriptor.quota_policy == ProviderQuotaPolicy(requests_per_minute=30, requests_per_day=1_000)
    assert descriptor.freshness_policy == ProviderFreshnessPolicy(max_age_seconds=300)


def _policy_log_records(caplog):
    return [
        record.provider_policy_decision
        for record in caplog.records
        if record.getMessage() == "provider_policy_decision"
    ]


def test_provider_policy_decision_log_records_allowed_context_without_sensitive_content(caplog):
    with caplog.at_level("INFO", logger="app.providers.registry"):
        DEFAULT_PROVIDER_REGISTRY.require_operation(
            "penaltyblog",
            "local-model",
            "goal_expectancy",
            context=ProviderExecutionContext.CANARY,
        )

    decisions = _policy_log_records(caplog)
    assert decisions == [
        {
            "adapter_key": "penaltyblog",
            "source_key": "local-model",
            "context": "canary",
            "operation": "goal_expectancy",
            "outcome": "allowed",
            "reason_code": "allowed",
        }
    ]
    assert "payload-secret" not in caplog.text


def test_provider_policy_decision_log_redacts_unknown_operation_details(caplog):
    with caplog.at_level("INFO", logger="app.providers.registry"):
        with pytest.raises(ProviderCapabilityError):
            DEFAULT_PROVIDER_REGISTRY.require_operation(
                "penaltyblog",
                "local-model",
                "unknown-operation-with-secret",
                context=ProviderExecutionContext.TEST,
            )

    decisions = _policy_log_records(caplog)
    assert decisions == [
        {
            "adapter_key": "penaltyblog",
            "source_key": "local-model",
            "context": "test",
            "outcome": "rejected",
            "reason_code": "unknown_operation",
        }
    ]
    assert "unknown-operation-with-secret" not in caplog.text


@pytest.mark.parametrize(
    "adapter_policy,source_policy,expected_reason",
    [
        (ProductionPolicy.ALLOWED, ProductionPolicy.APPROVAL_REQUIRED, "source_approval_required"),
        (ProductionPolicy.ALLOWED, ProductionPolicy.DISABLED, "source_disabled"),
        (ProductionPolicy.DISABLED, ProductionPolicy.ALLOWED, "adapter_disabled"),
    ],
)
def test_provider_policy_decision_log_captures_fail_closed_policy_outcome_without_reason_text(
    caplog, adapter_policy, source_policy, expected_reason
):
    adapter = ProviderDescriptor(
        key="example",
        display_name="Example",
        kind=ProviderKind.MODEL,
        transport=ProviderTransport.SUBPROCESS,
        capabilities=frozenset({ProviderCapability.PREDICTIONS}),
        production_policy=adapter_policy,
        policy_reason="adapter-private-policy-reason",
    )
    source = ProviderSourceDescriptor(
        adapter_key="example",
        source_key="local-model",
        capabilities=frozenset({ProviderCapability.PREDICTIONS}),
        production_policy=source_policy,
        policy_reason="source-private-policy-reason",
    )
    registry = ProviderRegistry(
        (adapter,),
        (source,),
        operation_capabilities={
            ("example", "local-model", "goal_expectancy"): ProviderCapability.PREDICTIONS,
        },
    )

    with caplog.at_level("INFO", logger="app.providers.registry"):
        with pytest.raises(ProviderPolicyError):
            registry.require_operation(
                "example", "local-model", "goal_expectancy", context=ProviderExecutionContext.TEST
            )

    decisions = _policy_log_records(caplog)
    expected = {
        "adapter_key": "example",
        "source_key": "local-model",
        "context": "test",
        "outcome": "rejected",
        "reason_code": expected_reason,
    }
    if expected_reason != "adapter_disabled":
        expected["operation"] = "goal_expectancy"
    assert decisions == [expected]
    assert "private-policy-reason" not in caplog.text


@pytest.mark.parametrize(
    "adapter_key,source_key,operation,expected_reason,expected_error,secret",
    [
        ("adapter-secret", "local-model", "goal_expectancy", "unknown_adapter", UnknownProviderError, "adapter-secret"),
        ("penaltyblog", "source-secret", "goal_expectancy", "unknown_source", UnknownProviderError, "source-secret"),
        (
            "penaltyblog",
            "local-model",
            "operation-secret",
            "unknown_operation",
            ProviderCapabilityError,
            "operation-secret",
        ),
    ],
)
def test_provider_policy_audit_and_errors_do_not_expose_unknown_secret_like_inputs(
    caplog, adapter_key, source_key, operation, expected_reason, expected_error, secret
):
    with caplog.at_level("INFO", logger="app.providers.registry"):
        with pytest.raises(expected_error) as raised:
            DEFAULT_PROVIDER_REGISTRY.require_operation(
                adapter_key, source_key, operation, context=ProviderExecutionContext.TEST
            )

    decisions = _policy_log_records(caplog)
    assert decisions[0]["context"] == "test"
    assert decisions[0]["outcome"] == "rejected"
    assert decisions[0]["reason_code"] == expected_reason
    assert secret not in str(raised.value)
    assert secret not in caplog.text


@pytest.mark.parametrize(
    ("operation", "capability"),
    (
        ("runtime_info", ProviderCapability.FEATURES),
        ("model_train", ProviderCapability.FEATURES),
        ("model_predict_batch", ProviderCapability.PREDICTIONS),
        ("model_backtest_fold", ProviderCapability.BACKTESTS),
        ("calculate_implied", ProviderCapability.FEATURES),
        ("dixon_coles_weights", ProviderCapability.FEATURES),
        ("model_fit_predict", ProviderCapability.PREDICTIONS),
    ),
)
def test_local_penaltyblog_model_artifact_operations_are_explicitly_policy_mapped(operation, capability):
    source = DEFAULT_PROVIDER_REGISTRY.require_operation(
        "penaltyblog", "local-model", operation, context=ProviderExecutionContext.PRODUCTION
    )

    assert source.supports(capability)
    assert capability_for_operation(operation, adapter_key="penaltyblog", source_key="local-model") is capability


@pytest.mark.parametrize("operation", ("scraper_fbref_fixtures", "scraper_understat_fixtures", "catalog"))
def test_penaltyblog_scraper_operations_remain_unmapped(operation):
    with pytest.raises(ProviderCapabilityError, match="Unknown provider operation"):
        DEFAULT_PROVIDER_REGISTRY.require_operation("penaltyblog", "local-model", operation)
