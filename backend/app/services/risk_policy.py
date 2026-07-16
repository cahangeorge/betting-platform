from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bankroll import LedgerEntry
from app.models.risk import BankrollRiskPolicy, BankrollRiskState
from app.models.ticket import Ticket
from app.schemas.risk import RiskPolicyWriteRequest, RiskUsageResponse
from app.services.portfolio_risk import RiskPolicy
from app.services.staking import StakingPolicy

RELAXATION_DELAY = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(UTC)


def _policy_values(body: RiskPolicyWriteRequest) -> dict[str, Any]:
    return body.model_dump(mode="json")


def _active_stmt(bankroll_id: int, now: datetime):
    return (
        select(BankrollRiskPolicy)
        .where(
            BankrollRiskPolicy.bankroll_id == bankroll_id,
            BankrollRiskPolicy.effective_from <= now,
            or_(BankrollRiskPolicy.superseded_at.is_(None), BankrollRiskPolicy.superseded_at > now),
        )
        .order_by(BankrollRiskPolicy.version.desc())
        .limit(1)
    )


async def load_risk_state(db: AsyncSession, bankroll_id: int) -> BankrollRiskState | None:
    return await db.get(BankrollRiskState, bankroll_id)


async def load_active_policy(
    db: AsyncSession,
    bankroll_id: int,
    *,
    now: datetime | None = None,
    promote_pending: bool = True,
) -> BankrollRiskPolicy | None:
    current_time = now or _now()
    if promote_pending:
        await promote_pending_policy(db, bankroll_id, now=current_time)
    result = await db.execute(_active_stmt(bankroll_id, current_time))
    return result.scalar_one_or_none()


def _is_relaxation(current: BankrollRiskPolicy, proposed: RiskPolicyWriteRequest) -> bool:
    for field in (
        "max_ticket_pct",
        "max_open_exposure_pct",
        "max_match_pct",
        "max_team_pct",
        "max_league_window_pct",
        "max_daily_stake_pct",
        "max_weekly_stake_pct",
    ):
        if Decimal(str(getattr(proposed, field))) > Decimal(str(getattr(current, field))):
            return True
    for field in ("max_daily_ticket_count", "max_weekly_ticket_count"):
        if int(getattr(proposed, field)) > int(getattr(current, field)):
            return True
    # A shorter rolling window excludes more same-league kickoffs and is
    # therefore a relaxation; increasing it is conservative tightening.
    if proposed.league_window_hours < current.league_window_hours:
        return True
    if proposed.accumulators_enabled and not current.accumulators_enabled:
        return True
    if proposed.automation_enabled and not current.automation_enabled:
        return True
    if proposed.staking_mode != current.staking_mode:
        return True
    if proposed.flat_stake_pct is not None and current.flat_stake_pct is not None:
        if proposed.flat_stake_pct > current.flat_stake_pct:
            return True
    if proposed.kelly_fraction is not None and current.kelly_fraction is not None:
        if proposed.kelly_fraction > current.kelly_fraction:
            return True
    return False


def _new_policy(
    *,
    bankroll_id: int,
    user_id: int,
    version: int,
    effective_from: datetime,
    body: RiskPolicyWriteRequest,
) -> BankrollRiskPolicy:
    return BankrollRiskPolicy(
        bankroll_id=bankroll_id,
        version=version,
        effective_from=effective_from,
        created_by_user_id=user_id,
        **_policy_values(body),
    )


async def promote_pending_policy(
    db: AsyncSession,
    bankroll_id: int,
    *,
    now: datetime | None = None,
) -> BankrollRiskPolicy | None:
    current_time = now or _now()
    state = await load_risk_state(db, bankroll_id)
    if (
        state is None
        or not isinstance(state.pending_policy, dict)
        or state.pending_effective_at is None
        or state.pending_effective_at > current_time
    ):
        return None

    current_result = await db.execute(_active_stmt(bankroll_id, current_time))
    current = current_result.scalar_one_or_none()
    next_version = (current.version if current else 0) + 1
    if current is not None:
        current.superseded_at = current_time
        await db.flush()
    body = RiskPolicyWriteRequest.model_validate(state.pending_policy)
    policy = _new_policy(
        bankroll_id=bankroll_id,
        user_id=state.updated_by_user_id or (current.created_by_user_id if current else 0),
        version=next_version,
        effective_from=current_time,
        body=body,
    )
    db.add(policy)
    state.pending_policy = None
    state.pending_effective_at = None
    await db.flush()
    return policy


async def upsert_risk_policy(
    db: AsyncSession,
    *,
    bankroll_id: int,
    user_id: int,
    body: RiskPolicyWriteRequest,
    now: datetime | None = None,
) -> tuple[BankrollRiskPolicy | None, datetime | None]:
    current_time = now or _now()
    current = await load_active_policy(db, bankroll_id, now=current_time)
    state = await load_risk_state(db, bankroll_id)
    if state is None:
        state = BankrollRiskState(bankroll_id=bankroll_id, updated_by_user_id=user_id)
        db.add(state)

    if current is not None and _is_relaxation(current, body):
        state.pending_policy = _policy_values(body)
        state.pending_effective_at = current_time + RELAXATION_DELAY
        state.updated_by_user_id = user_id
        await db.flush()
        return current, state.pending_effective_at

    if current is not None:
        current.superseded_at = current_time
        await db.flush()
    policy = _new_policy(
        bankroll_id=bankroll_id,
        user_id=user_id,
        version=(current.version if current else 0) + 1,
        effective_from=current_time,
        body=body,
    )
    db.add(policy)
    state.pending_policy = None
    state.pending_effective_at = None
    state.updated_by_user_id = user_id
    await db.flush()
    return policy, None


async def pause_bankroll(
    db: AsyncSession,
    *,
    bankroll_id: int,
    user_id: int,
    paused_until: datetime,
    reason: str | None,
    now: datetime | None = None,
) -> BankrollRiskState:
    current_time = now or _now()
    requested_until = paused_until.astimezone(UTC)
    if requested_until <= current_time or requested_until > current_time + timedelta(days=365):
        raise ValueError("paused_until must be in the future and no more than 365 days away")
    state = await load_risk_state(db, bankroll_id)
    if state is None:
        state = BankrollRiskState(bankroll_id=bankroll_id)
        db.add(state)
    if state.paused_until is None or state.paused_until < requested_until:
        state.paused_until = requested_until
        state.pause_reason = reason
    state.updated_by_user_id = user_id
    await db.flush()
    return state


async def load_risk_usage(
    db: AsyncSession,
    *,
    bankroll_id: int,
    now: datetime | None = None,
) -> RiskUsageResponse:
    current_time = now or _now()
    day_ago = current_time - timedelta(hours=24)
    week_ago = current_time - timedelta(days=7)
    open_result = await db.execute(
        select(func.coalesce(func.sum(Ticket.stake), 0)).where(
            Ticket.bankroll_id == bankroll_id,
            Ticket.status.in_(("open", "watchlist")),
        )
    )
    aggregates = await db.execute(
        select(
            func.coalesce(func.sum(LedgerEntry.amount).filter(LedgerEntry.created_at >= day_ago), 0),
            func.coalesce(func.sum(LedgerEntry.amount).filter(LedgerEntry.created_at >= week_ago), 0),
            func.count(LedgerEntry.id).filter(LedgerEntry.created_at >= day_ago),
            func.count(LedgerEntry.id).filter(LedgerEntry.created_at >= week_ago),
        ).where(LedgerEntry.bankroll_id == bankroll_id, LedgerEntry.entry_type == "stake")
    )
    day_amount, week_amount, day_count, week_count = aggregates.one()
    return RiskUsageResponse(
        open_exposure_amount=abs(Decimal(str(open_result.scalar_one()))),
        staked_last_24h=abs(Decimal(str(day_amount))),
        staked_last_7d=abs(Decimal(str(week_amount))),
        ticket_count_last_24h=int(day_count),
        ticket_count_last_7d=int(week_count),
    )


def orm_policy_to_domain(
    policy: BankrollRiskPolicy,
    *,
    paused_until: datetime | None,
) -> RiskPolicy:
    staking = StakingPolicy(
        mode=policy.staking_mode,
        flat_stake_percent=Decimal(str(policy.flat_stake_pct)) * 100 if policy.flat_stake_pct is not None else None,
        kelly_fraction=policy.kelly_fraction,
    )
    return RiskPolicy(
        version=str(policy.version),
        staking=staking,
        max_ticket_percent=Decimal(str(policy.max_ticket_pct)) * 100,
        max_open_exposure_percent=Decimal(str(policy.max_open_exposure_pct)) * 100,
        max_daily_stake_percent=Decimal(str(policy.max_daily_stake_pct)) * 100,
        max_weekly_stake_percent=Decimal(str(policy.max_weekly_stake_pct)) * 100,
        max_daily_ticket_count=policy.max_daily_ticket_count,
        max_weekly_ticket_count=policy.max_weekly_ticket_count,
        max_match_exposure_percent=Decimal(str(policy.max_match_pct)) * 100,
        max_team_exposure_percent=Decimal(str(policy.max_team_pct)) * 100,
        max_league_window_exposure_percent=Decimal(str(policy.max_league_window_pct)) * 100,
        league_window_hours=policy.league_window_hours,
        accumulators_enabled=policy.accumulators_enabled,
        automation_enabled=policy.automation_enabled,
        paused_until=paused_until,
    )
