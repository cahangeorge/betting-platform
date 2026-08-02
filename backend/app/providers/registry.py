import logging
import re
from types import MappingProxyType
from typing import Iterable, Mapping

from app.providers.contracts import (
    ProductionPolicy,
    ProviderCapability,
    ProviderDescriptor,
    ProviderExecutionContext,
    ProviderFreshnessPolicy,
    ProviderKind,
    ProviderQuotaPolicy,
    ProviderSourceDescriptor,
    ProviderTransport,
)


class UnknownProviderError(LookupError):
    pass


class ProviderCapabilityError(ValueError):
    pass


class ProviderPolicyError(PermissionError):
    pass


logger = logging.getLogger(__name__)
_SAFE_LOG_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_SAFE_LOG_OPERATION_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


# Legacy operation-only view. New gates resolve the full adapter/source/operation identity.
OPERATION_CAPABILITIES: Mapping[str, ProviderCapability] = MappingProxyType(
    {"goal_expectancy": ProviderCapability.PREDICTIONS}
)
SOURCE_OPERATION_CAPABILITIES: Mapping[tuple[str, str, str], ProviderCapability] = MappingProxyType(
    {
        ("penaltyblog", "local-model", "goal_expectancy"): ProviderCapability.PREDICTIONS,
        # Model-artifact operations are backend-owned and deliberately limited
        # to the local penaltyblog adapter. Scraper operations remain unmapped.
        ("penaltyblog", "local-model", "runtime_info"): ProviderCapability.FEATURES,
        ("penaltyblog", "local-model", "model_train"): ProviderCapability.FEATURES,
        ("penaltyblog", "local-model", "model_predict_batch"): ProviderCapability.PREDICTIONS,
        ("penaltyblog", "local-model", "model_backtest_fold"): ProviderCapability.BACKTESTS,
        ("penaltyblog", "local-model", "calculate_implied"): ProviderCapability.FEATURES,
        ("penaltyblog", "local-model", "dixon_coles_weights"): ProviderCapability.FEATURES,
        ("penaltyblog", "local-model", "model_fit_predict"): ProviderCapability.PREDICTIONS,
        ("soccerdata", "football-data-co-uk", "matchhistory_results_backfill"): ProviderCapability.RESULTS,
        ("soccerdata", "espn", "espn_schedule_incremental"): ProviderCapability.FIXTURES,
        ("soccerdata", "fbref", "fbref_schedule_backfill"): ProviderCapability.FIXTURES,
        ("soccerdata", "fbref", "fbref_team_stats_backfill"): ProviderCapability.STATISTICS,
        ("soccerdata", "understat", "understat_schedule_backfill"): ProviderCapability.FIXTURES,
        ("soccerdata", "understat", "understat_team_stats_backfill"): ProviderCapability.STATISTICS,
        ("sportmonks-v3-odds", "sportmonks-football-v3-standard-odds", "fetch_latest_odds"): ProviderCapability.ODDS,
        ("oddsharvester", "oddsportal", "fetch_odds_snapshot"): ProviderCapability.ODDS,
    }
)


def capability_for_operation(
    operation: str,
    *,
    adapter_key: str | None = None,
    source_key: str | None = None,
) -> ProviderCapability:
    if (adapter_key is None) != (source_key is None):
        raise ProviderCapabilityError("Provider operation identity is incomplete")
    if adapter_key is not None and source_key is not None:
        try:
            return SOURCE_OPERATION_CAPABILITIES[(adapter_key, source_key, operation)]
        except KeyError as exc:
            raise ProviderCapabilityError("Unknown provider operation") from exc
    try:
        return OPERATION_CAPABILITIES[operation]
    except KeyError as exc:
        raise ProviderCapabilityError("Unknown provider operation") from exc


class ProviderRegistry:
    def __init__(
        self,
        providers: Iterable[ProviderDescriptor],
        sources: Iterable[ProviderSourceDescriptor] = (),
        *,
        operation_capabilities: Mapping[tuple[str, str, str], ProviderCapability] | None = None,
    ):
        by_key: dict[str, ProviderDescriptor] = {}
        for provider in providers:
            if provider.key in by_key:
                raise ValueError(f"Duplicate provider key: {provider.key}")
            by_key[provider.key] = provider
        by_source: dict[tuple[str, str], ProviderSourceDescriptor] = {}
        for source in sources:
            adapter = by_key.get(source.adapter_key)
            if adapter is None:
                raise ValueError(f"Provider source references unknown adapter: {source.adapter_key}")
            if not source.capabilities.issubset(adapter.capabilities):
                raise ValueError(
                    f"Provider source {source.adapter_key}/{source.source_key} exceeds adapter capabilities"
                )
            identity = (source.adapter_key, source.source_key)
            if identity in by_source:
                raise ValueError(f"Duplicate provider source: {source.adapter_key}/{source.source_key}")
            by_source[identity] = source
        self._providers: Mapping[str, ProviderDescriptor] = MappingProxyType(by_key)
        self._sources: Mapping[tuple[str, str], ProviderSourceDescriptor] = MappingProxyType(by_source)
        operations = SOURCE_OPERATION_CAPABILITIES if operation_capabilities is None else operation_capabilities
        self._operation_capabilities: Mapping[tuple[str, str, str], ProviderCapability] = MappingProxyType(
            {
                (adapter_key, source_key, operation): ProviderCapability(capability)
                for (adapter_key, source_key, operation), capability in operations.items()
            }
        )

    def get(self, provider_key: str) -> ProviderDescriptor:
        try:
            return self._providers[provider_key]
        except KeyError as exc:
            raise UnknownProviderError("Unknown provider") from exc

    def get_source(self, adapter_key: str, source_key: str) -> ProviderSourceDescriptor:
        self.get(adapter_key)
        try:
            return self._sources[(adapter_key, source_key)]
        except KeyError as exc:
            raise UnknownProviderError("Unknown provider source") from exc

    def list(self) -> tuple[ProviderDescriptor, ...]:
        return tuple(self._providers[key] for key in sorted(self._providers))

    def list_sources(self) -> tuple[ProviderSourceDescriptor, ...]:
        return tuple(self._sources[key] for key in sorted(self._sources))

    def require_capability(
        self,
        provider_key: str,
        capability: ProviderCapability,
        *,
        allow_unapproved: bool | None = None,
    ) -> ProviderDescriptor:
        """Legacy adapter-level gate; retained keyword has no bypass effect."""
        del allow_unapproved
        provider = self.get(provider_key)
        if not provider.supports(capability):
            raise ProviderCapabilityError(f"Provider {provider_key} does not provide {capability.value}")
        self._require_policy(provider.production_policy, provider.policy_reason)
        return provider

    def require_operation(
        self,
        adapter_key: str,
        source_key: str,
        operation: str,
        *,
        context: ProviderExecutionContext = ProviderExecutionContext.PRODUCTION,
    ) -> ProviderSourceDescriptor:
        """Fail-closed upstream-scoped operation gate used by bridge callers."""
        try:
            context = ProviderExecutionContext(context)
        except ValueError as exc:
            self._log_policy_decision(
                adapter_key="<invalid>",
                source_key="<invalid>",
                context=context,
                outcome="rejected",
                reason_code="invalid_context",
            )
            raise ProviderPolicyError("Provider execution context is invalid") from exc
        try:
            adapter = self.get(adapter_key)
        except UnknownProviderError:
            self._log_policy_decision(
                adapter_key="<invalid>",
                source_key="<invalid>",
                context=context,
                outcome="rejected",
                reason_code="unknown_adapter",
            )
            raise
        try:
            source = self.get_source(adapter_key, source_key)
        except UnknownProviderError:
            self._log_policy_decision(
                adapter_key=adapter_key,
                source_key="<invalid>",
                context=context,
                outcome="rejected",
                reason_code="unknown_source",
            )
            raise
        # An adapter-level execution ban dominates every upstream source policy.
        if adapter.production_policy is ProductionPolicy.DISABLED:
            self._log_policy_decision(
                adapter_key=adapter_key,
                source_key=source_key,
                context=context,
                outcome="rejected",
                reason_code="adapter_disabled",
            )
            raise ProviderPolicyError(adapter.policy_reason)
        try:
            capability = self._operation_capabilities[(adapter_key, source_key, operation)]
        except KeyError as exc:
            self._log_policy_decision(
                adapter_key=adapter_key,
                source_key=source_key,
                context=context,
                outcome="rejected",
                reason_code="unknown_operation",
            )
            raise ProviderCapabilityError("Unknown provider operation") from exc
        if not adapter.supports(capability) or not source.supports(capability):
            self._log_policy_decision(
                adapter_key=adapter_key,
                source_key=source_key,
                context=context,
                outcome="rejected",
                reason_code="capability_not_supported",
                operation=operation,
            )
            raise ProviderCapabilityError(
                f"Provider source {adapter_key}/{source_key} does not provide {capability.value}"
            )
        # Context is explicit for auditability, but does not silently bypass policy.
        if source.production_policy is not ProductionPolicy.ALLOWED:
            self._log_policy_decision(
                adapter_key=adapter_key,
                source_key=source_key,
                context=context,
                outcome="rejected",
                reason_code=f"source_{source.production_policy.value}",
                operation=operation,
            )
            raise ProviderPolicyError(source.policy_reason)
        self._log_policy_decision(
            adapter_key=adapter_key,
            source_key=source_key,
            context=context,
            outcome="allowed",
            reason_code="allowed",
            operation=operation,
        )
        return source

    @staticmethod
    def _log_policy_decision(
        *,
        adapter_key: object,
        source_key: object,
        context: object,
        outcome: str,
        reason_code: str,
        operation: str | None = None,
    ) -> None:
        def safe_identifier(value: object) -> str:
            return value if isinstance(value, str) and _SAFE_LOG_KEY_PATTERN.fullmatch(value) else "<invalid>"

        def safe_operation(value: object) -> str:
            return value if isinstance(value, str) and _SAFE_LOG_OPERATION_PATTERN.fullmatch(value) else "<invalid>"

        decision: dict[str, str] = {
            "adapter_key": safe_identifier(adapter_key),
            "source_key": safe_identifier(source_key),
            "context": context.value if isinstance(context, ProviderExecutionContext) else "<invalid>",
            "outcome": outcome,
            "reason_code": reason_code,
        }
        if operation is not None:
            decision["operation"] = safe_operation(operation)
        logger.info("provider_policy_decision", extra={"provider_policy_decision": decision})

    @staticmethod
    def _require_policy(
        policy: ProductionPolicy,
        reason: str,
    ) -> None:
        if policy is ProductionPolicy.ALLOWED:
            return
        if policy is ProductionPolicy.DISABLED:
            raise ProviderPolicyError(reason)
        if policy is ProductionPolicy.APPROVAL_REQUIRED:
            raise ProviderPolicyError(reason)
        raise ProviderPolicyError("Provider has an unsupported production policy")


DEFAULT_PROVIDER_REGISTRY = ProviderRegistry(
    (
        ProviderDescriptor(
            key="sportmonks-v3-odds",
            display_name="Sportmonks Football API v3",
            kind=ProviderKind.ODDS,
            transport=ProviderTransport.API,
            capabilities=frozenset({ProviderCapability.ODDS}),
            production_policy=ProductionPolicy.APPROVAL_REQUIRED,
            policy_reason="Sportmonks production use requires an approved licence, quota and retention record.",
        ),
        ProviderDescriptor(
            key="oddsharvester",
            display_name="OddsHarvester",
            kind=ProviderKind.ODDS,
            transport=ProviderTransport.SUBPROCESS,
            capabilities=frozenset({ProviderCapability.FIXTURES, ProviderCapability.RESULTS, ProviderCapability.ODDS}),
            production_policy=ProductionPolicy.APPROVAL_REQUIRED,
            policy_reason="OddsHarvester production use requires explicit upstream approval for automated access.",
        ),
        ProviderDescriptor(
            key="soccerdata",
            display_name="soccerdata",
            kind=ProviderKind.DATA,
            transport=ProviderTransport.SUBPROCESS,
            capabilities=frozenset(
                {
                    ProviderCapability.FIXTURES,
                    ProviderCapability.RESULTS,
                    ProviderCapability.STATISTICS,
                    ProviderCapability.LINEUPS,
                    ProviderCapability.INJURIES,
                    ProviderCapability.RATINGS,
                }
            ),
            production_policy=ProductionPolicy.APPROVAL_REQUIRED,
            policy_reason="soccerdata production use requires approval for each selected upstream source.",
        ),
        ProviderDescriptor(
            key="penaltyblog",
            display_name="penaltyblog",
            kind=ProviderKind.MODEL,
            transport=ProviderTransport.SUBPROCESS,
            capabilities=frozenset(
                {
                    ProviderCapability.FEATURES,
                    ProviderCapability.RATINGS,
                    ProviderCapability.PREDICTIONS,
                    ProviderCapability.BACKTESTS,
                }
            ),
            production_policy=ProductionPolicy.ALLOWED,
        ),
        ProviderDescriptor(
            key="flumine",
            display_name="flumine",
            kind=ProviderKind.EXECUTION,
            transport=ProviderTransport.LIBRARY,
            capabilities=frozenset({ProviderCapability.EXECUTION}),
            production_policy=ProductionPolicy.DISABLED,
            policy_reason="Flumine execution is excluded from the public MVP.",
        ),
    ),
    (
        ProviderSourceDescriptor(
            adapter_key="sportmonks-v3-odds",
            source_key="sportmonks-football-v3-standard-odds",
            capabilities=frozenset({ProviderCapability.ODDS}),
            production_policy=ProductionPolicy.APPROVAL_REQUIRED,
            policy_reason="Sportmonks API access requires an approved licence, quota and retention record.",
            quota_policy=ProviderQuotaPolicy(requests_per_minute=60),
            freshness_policy=ProviderFreshnessPolicy(max_age_seconds=300),
            # No raw source body is retained before a rights/retention decision.
            body_retention_days=None,
        ),
        ProviderSourceDescriptor(
            adapter_key="oddsharvester",
            source_key="oddsportal",
            capabilities=frozenset({ProviderCapability.FIXTURES, ProviderCapability.RESULTS, ProviderCapability.ODDS}),
            production_policy=ProductionPolicy.APPROVAL_REQUIRED,
            policy_reason="OddsPortal browser acquisition requires explicit automated-access and retention approval.",
            quota_policy=ProviderQuotaPolicy(requests_per_minute=2),
            freshness_policy=ProviderFreshnessPolicy(max_age_seconds=300),
            body_retention_days=None,
        ),
        ProviderSourceDescriptor(
            adapter_key="penaltyblog",
            source_key="local-model",
            # Backend-owned model-artifact operations are explicitly allowlisted.
            # No penaltyblog scraping operation is policy-mapped.
            capabilities=frozenset(
                {
                    ProviderCapability.FEATURES,
                    ProviderCapability.PREDICTIONS,
                    ProviderCapability.BACKTESTS,
                }
            ),
            production_policy=ProductionPolicy.ALLOWED,
            quota_policy=ProviderQuotaPolicy.unlimited(),
            freshness_policy=ProviderFreshnessPolicy.not_applicable(),
        ),
        ProviderSourceDescriptor(
            adapter_key="soccerdata",
            source_key="football-data-co-uk",
            capabilities=frozenset({ProviderCapability.RESULTS}),
            production_policy=ProductionPolicy.APPROVAL_REQUIRED,
            policy_reason="Football-Data automated production use requires an approved rights and retention record.",
            quota_policy=ProviderQuotaPolicy(requests_per_minute=10),
            freshness_policy=ProviderFreshnessPolicy(max_age_seconds=86_400),
        ),
        ProviderSourceDescriptor(
            adapter_key="soccerdata",
            source_key="espn",
            capabilities=frozenset({ProviderCapability.FIXTURES, ProviderCapability.RESULTS}),
            production_policy=ProductionPolicy.APPROVAL_REQUIRED,
            policy_reason="ESPN automated production use requires an approved rights and retention record.",
            quota_policy=ProviderQuotaPolicy(requests_per_minute=30),
            freshness_policy=ProviderFreshnessPolicy(max_age_seconds=900),
        ),
        ProviderSourceDescriptor(
            adapter_key="soccerdata",
            source_key="fbref",
            capabilities=frozenset(
                {
                    ProviderCapability.FIXTURES,
                    ProviderCapability.RESULTS,
                    ProviderCapability.STATISTICS,
                    ProviderCapability.LINEUPS,
                }
            ),
            production_policy=ProductionPolicy.APPROVAL_REQUIRED,
            policy_reason="FBref browser automation requires an approved rights and retention record.",
            quota_policy=ProviderQuotaPolicy(requests_per_minute=6),
            freshness_policy=ProviderFreshnessPolicy(max_age_seconds=86_400),
        ),
        ProviderSourceDescriptor(
            adapter_key="soccerdata",
            source_key="understat",
            capabilities=frozenset(
                {ProviderCapability.FIXTURES, ProviderCapability.RESULTS, ProviderCapability.STATISTICS}
            ),
            production_policy=ProductionPolicy.APPROVAL_REQUIRED,
            policy_reason="Understat automated production use requires an approved rights and retention record.",
            quota_policy=ProviderQuotaPolicy(requests_per_minute=10),
            freshness_policy=ProviderFreshnessPolicy(max_age_seconds=21_600),
        ),
    ),
)
