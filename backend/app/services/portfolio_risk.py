"""Pure portfolio risk assessment for paper betting tickets.

Callers are responsible for loading the policy and current exposure under the
appropriate database lock.  This module only evaluates an immutable snapshot,
making it suitable for preflight, generation, refresh, and activation checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, TypeAlias

from app.services.staking import (
    HARD_MAX_TICKET_PERCENT,
    ONE_HUNDRED,
    DecimalInput,
    StakingMode,
    StakingPolicy,
    quantize_money,
    to_decimal,
)

RiskKey: TypeAlias = int | str
HARD_MAX_OPEN_EXPOSURE_PERCENT = Decimal("20")


class RiskPolicyError(ValueError):
    """A stable, machine-readable policy validation error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _percent(value: DecimalInput, *, field: str, maximum: Decimal) -> Decimal:
    converted = to_decimal(value, field=field)
    if converted <= 0 or converted > maximum:
        raise RiskPolicyError(
            "invalid_risk_policy",
            f"{field} must be greater than 0 and no greater than {maximum}",
        )
    return converted


def _positive_count(value: int, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RiskPolicyError("invalid_risk_policy", f"{field} must be a positive integer")
    return value


def _aware_datetime(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RiskPolicyError("invalid_risk_policy", f"{field} must be timezone-aware")
    return value


def _money(value: DecimalInput, *, field: str) -> Decimal:
    converted = quantize_money(to_decimal(value, field=field))
    if converted < 0:
        raise RiskPolicyError("invalid_risk_context", f"{field} must be zero or greater")
    return converted


def _exposure_map(values: Mapping[RiskKey, DecimalInput], *, field: str) -> Mapping[RiskKey, Decimal]:
    normalized = {key: _money(value, field=f"{field}[{key}]") for key, value in values.items()}
    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    """A complete, explicitly configured paper-risk policy."""

    version: str
    staking: StakingPolicy
    max_ticket_percent: DecimalInput
    max_open_exposure_percent: DecimalInput
    max_daily_stake_percent: DecimalInput
    max_weekly_stake_percent: DecimalInput
    max_daily_ticket_count: int
    max_weekly_ticket_count: int
    max_match_exposure_percent: DecimalInput
    max_team_exposure_percent: DecimalInput
    max_league_window_exposure_percent: DecimalInput
    league_window_hours: int
    accumulators_enabled: bool
    automation_enabled: bool
    paused_until: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise RiskPolicyError("invalid_risk_policy", "version must be a non-empty string")
        if not isinstance(self.staking, StakingPolicy):
            raise RiskPolicyError("invalid_risk_policy", "staking must be a validated StakingPolicy")
        if not isinstance(self.accumulators_enabled, bool) or not isinstance(self.automation_enabled, bool):
            raise RiskPolicyError(
                "invalid_risk_policy",
                "accumulators_enabled and automation_enabled must be booleans",
            )

        percent_fields = (
            ("max_ticket_percent", HARD_MAX_TICKET_PERCENT),
            ("max_open_exposure_percent", HARD_MAX_OPEN_EXPOSURE_PERCENT),
            ("max_daily_stake_percent", ONE_HUNDRED),
            ("max_weekly_stake_percent", ONE_HUNDRED),
            ("max_match_exposure_percent", ONE_HUNDRED),
            ("max_team_exposure_percent", ONE_HUNDRED),
            ("max_league_window_exposure_percent", ONE_HUNDRED),
        )
        for field, maximum in percent_fields:
            object.__setattr__(self, field, _percent(getattr(self, field), field=field, maximum=maximum))
        object.__setattr__(
            self,
            "max_daily_ticket_count",
            _positive_count(self.max_daily_ticket_count, field="max_daily_ticket_count"),
        )
        object.__setattr__(
            self,
            "max_weekly_ticket_count",
            _positive_count(self.max_weekly_ticket_count, field="max_weekly_ticket_count"),
        )
        object.__setattr__(
            self,
            "league_window_hours",
            _positive_count(self.league_window_hours, field="league_window_hours"),
        )
        if self.league_window_hours > 24:
            raise RiskPolicyError("invalid_risk_policy", "league_window_hours cannot exceed 24")
        if self.max_daily_ticket_count > self.max_weekly_ticket_count:
            raise RiskPolicyError(
                "invalid_risk_policy",
                "max_daily_ticket_count cannot exceed max_weekly_ticket_count",
            )
        if self.max_daily_stake_percent > self.max_weekly_stake_percent:
            raise RiskPolicyError(
                "invalid_risk_policy",
                "max_daily_stake_percent cannot exceed max_weekly_stake_percent",
            )
        if self.paused_until is not None:
            object.__setattr__(self, "paused_until", _aware_datetime(self.paused_until, field="paused_until"))


@dataclass(frozen=True, slots=True)
class LeagueExposure:
    """One ticket's stake exposure at one league kickoff.

    ``exposure_id`` groups multiple legs belonging to the same ticket so the
    ticket stake is counted only once inside any evaluated rolling window.
    """

    exposure_id: RiskKey
    league_id: RiskKey
    kickoff: datetime
    stake: DecimalInput

    def __post_init__(self) -> None:
        if not isinstance(self.exposure_id, (int, str)) or isinstance(self.exposure_id, bool):
            raise RiskPolicyError("invalid_risk_context", "league exposure_id must be an integer or string")
        if not isinstance(self.league_id, (int, str)) or isinstance(self.league_id, bool):
            raise RiskPolicyError("invalid_risk_context", "league league_id must be an integer or string")
        object.__setattr__(self, "kickoff", _aware_datetime(self.kickoff, field="league kickoff"))
        stake = _money(self.stake, field="league stake")
        if stake <= 0:
            raise RiskPolicyError("invalid_risk_context", "league stake must be greater than zero")
        object.__setattr__(self, "stake", stake)


@dataclass(frozen=True, slots=True)
class PortfolioExposure:
    open_total: DecimalInput
    staked_last_24h: DecimalInput
    staked_last_7d: DecimalInput
    ticket_count_last_24h: int
    ticket_count_last_7d: int
    by_match: Mapping[RiskKey, DecimalInput]
    by_team: Mapping[RiskKey, DecimalInput]
    league_exposures: tuple[LeagueExposure, ...]

    def __post_init__(self) -> None:
        for field in ("open_total", "staked_last_24h", "staked_last_7d"):
            object.__setattr__(self, field, _money(getattr(self, field), field=field))
        for field in ("ticket_count_last_24h", "ticket_count_last_7d"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RiskPolicyError("invalid_risk_context", f"{field} must be a non-negative integer")
        object.__setattr__(self, "by_match", _exposure_map(self.by_match, field="by_match"))
        object.__setattr__(self, "by_team", _exposure_map(self.by_team, field="by_team"))
        league_exposures = tuple(self.league_exposures)
        if any(not isinstance(item, LeagueExposure) for item in league_exposures):
            raise RiskPolicyError("invalid_risk_context", "league_exposures must contain LeagueExposure values")
        stakes_by_exposure: dict[RiskKey, Decimal] = {}
        for item in league_exposures:
            previous = stakes_by_exposure.setdefault(item.exposure_id, item.stake)
            if previous != item.stake:
                raise RiskPolicyError(
                    "invalid_risk_context",
                    "all league exposure events for one ticket must use the same stake",
                )
        object.__setattr__(self, "league_exposures", league_exposures)


@dataclass(frozen=True, slots=True)
class RiskContext:
    bankroll_amount: DecimalInput
    available_balance: DecimalInput
    exposure: PortfolioExposure
    now: datetime

    def __post_init__(self) -> None:
        bankroll = _money(self.bankroll_amount, field="bankroll_amount")
        available = _money(self.available_balance, field="available_balance")
        if bankroll <= 0:
            raise RiskPolicyError("invalid_risk_context", "bankroll_amount must be greater than 0")
        if not isinstance(self.exposure, PortfolioExposure):
            raise RiskPolicyError("invalid_risk_context", "exposure must be a PortfolioExposure")
        object.__setattr__(self, "bankroll_amount", bankroll)
        object.__setattr__(self, "available_balance", available)
        object.__setattr__(self, "now", _aware_datetime(self.now, field="now"))


@dataclass(frozen=True, slots=True)
class RiskCandidate:
    stake: DecimalInput
    ticket_format: str
    match_ids: frozenset[RiskKey]
    team_ids: frozenset[RiskKey]
    league_ids: frozenset[RiskKey]
    league_kickoffs: Mapping[RiskKey, tuple[datetime, ...]]
    accumulator_risk_acknowledged: bool
    is_automated: bool

    def __post_init__(self) -> None:
        stake = _money(self.stake, field="stake")
        if stake <= 0:
            raise RiskPolicyError("invalid_risk_candidate", "stake must be greater than 0")
        normalized_format = self.ticket_format.strip().lower()
        if normalized_format not in {"single", "double", "treble"}:
            raise RiskPolicyError("invalid_risk_candidate", f"Unsupported ticket format: {self.ticket_format}")
        if not isinstance(self.accumulator_risk_acknowledged, bool) or not isinstance(self.is_automated, bool):
            raise RiskPolicyError(
                "invalid_risk_candidate",
                "accumulator_risk_acknowledged and is_automated must be booleans",
            )
        object.__setattr__(self, "stake", stake)
        object.__setattr__(self, "ticket_format", normalized_format)
        for field in ("match_ids", "team_ids", "league_ids"):
            object.__setattr__(self, field, frozenset(getattr(self, field)))
        normalized_kickoffs: dict[RiskKey, tuple[datetime, ...]] = {}
        for league_id, kickoffs in self.league_kickoffs.items():
            normalized_kickoffs[league_id] = tuple(
                sorted({_aware_datetime(kickoff, field=f"league_kickoffs[{league_id}]") for kickoff in kickoffs})
            )
        object.__setattr__(self, "league_kickoffs", MappingProxyType(normalized_kickoffs))


@dataclass(frozen=True, slots=True)
class RiskFinding:
    code: str
    message: str
    scope: str
    current: Decimal | int | None = None
    proposed: Decimal | int | None = None
    projected: Decimal | int | None = None
    limit: Decimal | int | None = None
    key: RiskKey | None = None


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    policy_version: str | None
    allowed: bool
    blockers: tuple[RiskFinding, ...]
    warnings: tuple[RiskFinding, ...]

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.blockers)


def _amount_for_percent(bankroll: Decimal, percent: Decimal) -> Decimal:
    return quantize_money(bankroll * percent / ONE_HUNDRED)


def _limit_finding(
    *,
    code: str,
    message: str,
    scope: str,
    current: Decimal | int,
    proposed: Decimal | int,
    projected: Decimal | int,
    limit: Decimal | int,
    key: RiskKey | None = None,
) -> RiskFinding:
    return RiskFinding(
        code=code,
        message=message,
        scope=scope,
        current=current,
        proposed=proposed,
        projected=projected,
        limit=limit,
        key=key,
    )


def _max_current_league_window_exposure(
    *,
    exposures: tuple[LeagueExposure, ...],
    league_id: RiskKey,
    candidate_kickoffs: tuple[datetime, ...],
    window_hours: int,
) -> Decimal:
    """Return the largest existing exposure in a rolling candidate window.

    Windows are half-open intervals ``[start, start + hours)``.  Every
    possible event start is evaluated, and only windows containing at least
    one proposed kickoff are relevant. Multiple legs from one existing ticket
    are deduplicated by ``exposure_id``.
    """

    league_events = tuple(item for item in exposures if item.league_id == league_id)
    starts = sorted({item.kickoff for item in league_events} | set(candidate_kickoffs))
    duration = timedelta(hours=window_hours)
    maximum = Decimal("0.00")
    for start in starts:
        end = start + duration
        if not any(start <= kickoff < end for kickoff in candidate_kickoffs):
            continue
        stake_by_exposure: dict[RiskKey, Decimal] = {}
        for item in league_events:
            if start <= item.kickoff < end:
                stake_by_exposure[item.exposure_id] = item.stake
        maximum = max(maximum, sum(stake_by_exposure.values(), Decimal("0.00")))
    return maximum


def assess_portfolio_risk(
    *,
    policy: RiskPolicy | None,
    context: RiskContext,
    candidate: RiskCandidate,
) -> RiskAssessment:
    """Fail-closed assessment of a proposed paper ticket against one snapshot."""

    if policy is None:
        missing = RiskFinding(
            code="risk_policy_required",
            message="An explicit risk policy must be configured before ticket generation",
            scope="policy",
        )
        return RiskAssessment(policy_version=None, allowed=False, blockers=(missing,), warnings=())

    blockers: list[RiskFinding] = []
    bankroll = context.bankroll_amount
    stake = candidate.stake

    if policy.paused_until is not None and policy.paused_until > context.now:
        blockers.append(
            RiskFinding(
                code="responsible_gambling_pause_active",
                message="Ticket generation is paused by the configured responsible-use policy",
                scope="policy",
            )
        )
    if candidate.is_automated and not policy.automation_enabled:
        blockers.append(
            RiskFinding(
                code="automation_disabled",
                message="Automated draft generation is disabled by the risk policy",
                scope="policy",
            )
        )

    is_accumulator = candidate.ticket_format != "single"
    if is_accumulator:
        if not policy.accumulators_enabled:
            blockers.append(
                RiskFinding(
                    code="accumulators_disabled",
                    message="Accumulator tickets are disabled by the risk policy",
                    scope="ticket",
                )
            )
        if not candidate.accumulator_risk_acknowledged:
            blockers.append(
                RiskFinding(
                    code="accumulator_acknowledgement_required",
                    message="Accumulator risk must be acknowledged explicitly",
                    scope="ticket",
                )
            )
        if policy.staking.mode is not StakingMode.FLAT_PERCENT:
            blockers.append(
                RiskFinding(
                    code="accumulator_flat_staking_required",
                    message="Accumulator tickets support flat-percent staking only",
                    scope="staking",
                )
            )

    if not candidate.match_ids:
        blockers.append(
            RiskFinding(
                code="risk_context_match_scope_required",
                message="Match identifiers are required to evaluate concentrated exposure",
                scope="match",
            )
        )
    if not candidate.team_ids:
        blockers.append(
            RiskFinding(
                code="risk_context_team_scope_required",
                message="Team identifiers are required to evaluate concentrated exposure",
                scope="team",
            )
        )
    if not candidate.league_ids:
        blockers.append(
            RiskFinding(
                code="risk_context_league_scope_required",
                message="League identifiers are required to evaluate concentrated exposure",
                scope="league_window",
            )
        )
    else:
        for league_id in sorted(candidate.league_ids, key=str):
            if not candidate.league_kickoffs.get(league_id):
                blockers.append(
                    RiskFinding(
                        code="risk_context_league_kickoff_required",
                        message="League kickoff timestamps are required to evaluate rolling exposure",
                        scope="league_window",
                        key=league_id,
                    )
                )

    if stake > context.available_balance:
        blockers.append(
            _limit_finding(
                code="insufficient_balance",
                message="The proposed stake exceeds the available bankroll balance",
                scope="bankroll",
                current=context.available_balance,
                proposed=stake,
                projected=stake,
                limit=context.available_balance,
            )
        )

    hard_ticket_limit = _amount_for_percent(bankroll, HARD_MAX_TICKET_PERCENT)
    if stake > hard_ticket_limit:
        blockers.append(
            _limit_finding(
                code="ticket_stake_hard_cap_exceeded",
                message="The proposed stake exceeds the platform hard cap of 5% per ticket",
                scope="ticket",
                current=Decimal("0.00"),
                proposed=stake,
                projected=stake,
                limit=hard_ticket_limit,
            )
        )
    policy_ticket_limit = _amount_for_percent(bankroll, policy.max_ticket_percent)
    if policy_ticket_limit < hard_ticket_limit and stake > policy_ticket_limit:
        blockers.append(
            _limit_finding(
                code="ticket_stake_policy_limit_exceeded",
                message="The proposed stake exceeds the configured per-ticket limit",
                scope="ticket",
                current=Decimal("0.00"),
                proposed=stake,
                projected=stake,
                limit=policy_ticket_limit,
            )
        )

    projected_open = context.exposure.open_total + stake
    hard_open_limit = _amount_for_percent(bankroll, HARD_MAX_OPEN_EXPOSURE_PERCENT)
    if projected_open > hard_open_limit:
        blockers.append(
            _limit_finding(
                code="open_exposure_hard_cap_exceeded",
                message="The projected open exposure exceeds the platform hard cap of 20%",
                scope="portfolio",
                current=context.exposure.open_total,
                proposed=stake,
                projected=projected_open,
                limit=hard_open_limit,
            )
        )
    policy_open_limit = _amount_for_percent(bankroll, policy.max_open_exposure_percent)
    if policy_open_limit < hard_open_limit and projected_open > policy_open_limit:
        blockers.append(
            _limit_finding(
                code="open_exposure_policy_limit_exceeded",
                message="The projected open exposure exceeds the configured portfolio limit",
                scope="portfolio",
                current=context.exposure.open_total,
                proposed=stake,
                projected=projected_open,
                limit=policy_open_limit,
            )
        )

    rolling_checks = (
        (
            "daily_stake_limit_exceeded",
            "The rolling 24-hour stake limit would be exceeded",
            "rolling_24h",
            context.exposure.staked_last_24h,
            _amount_for_percent(bankroll, policy.max_daily_stake_percent),
        ),
        (
            "weekly_stake_limit_exceeded",
            "The rolling 7-day stake limit would be exceeded",
            "rolling_7d",
            context.exposure.staked_last_7d,
            _amount_for_percent(bankroll, policy.max_weekly_stake_percent),
        ),
    )
    for code, message, scope, current, limit in rolling_checks:
        projected = current + stake
        if projected > limit:
            blockers.append(
                _limit_finding(
                    code=code,
                    message=message,
                    scope=scope,
                    current=current,
                    proposed=stake,
                    projected=projected,
                    limit=limit,
                )
            )

    count_checks = (
        (
            "daily_ticket_count_exceeded",
            "The rolling 24-hour ticket count limit would be exceeded",
            "rolling_24h",
            context.exposure.ticket_count_last_24h,
            policy.max_daily_ticket_count,
        ),
        (
            "weekly_ticket_count_exceeded",
            "The rolling 7-day ticket count limit would be exceeded",
            "rolling_7d",
            context.exposure.ticket_count_last_7d,
            policy.max_weekly_ticket_count,
        ),
    )
    for code, message, scope, current, limit in count_checks:
        projected = current + 1
        if projected > limit:
            blockers.append(
                _limit_finding(
                    code=code,
                    message=message,
                    scope=scope,
                    current=current,
                    proposed=1,
                    projected=projected,
                    limit=limit,
                )
            )

    entity_checks = (
        (
            "match_exposure_limit_exceeded",
            "The configured per-match exposure limit would be exceeded",
            "match",
            candidate.match_ids,
            context.exposure.by_match,
            policy.max_match_exposure_percent,
        ),
        (
            "team_exposure_limit_exceeded",
            "The configured per-team exposure limit would be exceeded",
            "team",
            candidate.team_ids,
            context.exposure.by_team,
            policy.max_team_exposure_percent,
        ),
    )
    for code, message, scope, keys, exposure_map, percent in entity_checks:
        limit = _amount_for_percent(bankroll, percent)
        for key in sorted(keys, key=str):
            current = exposure_map.get(key, Decimal("0.00"))
            projected = current + stake
            if projected > limit:
                blockers.append(
                    _limit_finding(
                        code=code,
                        message=message,
                        scope=scope,
                        current=current,
                        proposed=stake,
                        projected=projected,
                        limit=limit,
                        key=key,
                    )
                )

    league_limit = _amount_for_percent(bankroll, policy.max_league_window_exposure_percent)
    for league_id in sorted(candidate.league_ids, key=str):
        candidate_kickoffs = candidate.league_kickoffs.get(league_id, ())
        if not candidate_kickoffs:
            continue
        current = _max_current_league_window_exposure(
            exposures=context.exposure.league_exposures,
            league_id=league_id,
            candidate_kickoffs=candidate_kickoffs,
            window_hours=policy.league_window_hours,
        )
        projected = current + stake
        if projected > league_limit:
            blockers.append(
                _limit_finding(
                    code="league_window_exposure_limit_exceeded",
                    message=(
                        "The configured rolling league exposure limit would be exceeded "
                        f"within {policy.league_window_hours} hours"
                    ),
                    scope="league_window",
                    current=current,
                    proposed=stake,
                    projected=projected,
                    limit=league_limit,
                    key=league_id,
                )
            )

    return RiskAssessment(
        policy_version=policy.version,
        allowed=not blockers,
        blockers=tuple(blockers),
        warnings=(),
    )
