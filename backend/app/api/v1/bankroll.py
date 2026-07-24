from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.bankroll import Bankroll, BookmakerAccount, LedgerEntry
from app.models.user import User
from app.schemas.bankroll import (
    BankrollCreateRequest,
    BankrollResponse,
    BookmakerAccountCreateRequest,
    BookmakerAccountResponse,
    LedgerEntryResponse,
)
from app.schemas.risk import (
    RiskPauseRequest,
    RiskPauseStateResponse,
    RiskPolicyEnvelope,
    RiskPolicyResponse,
    RiskPolicyWriteRequest,
)
from app.services.risk_policy import (
    load_active_policy,
    load_risk_state,
    load_risk_usage,
    pause_bankroll,
    upsert_risk_policy,
)

router = APIRouter()


async def _owned_bankroll(db: AsyncSession, bankroll_id: int, user_id: int) -> Bankroll:
    result = await db.execute(select(Bankroll).where(Bankroll.id == bankroll_id, Bankroll.user_id == user_id))
    bankroll = result.scalar_one_or_none()
    if bankroll is None:
        raise HTTPException(status_code=404, detail="Bankroll not found")
    return bankroll


def _policy_response(policy) -> RiskPolicyResponse:
    return RiskPolicyResponse(
        id=policy.id,
        bankroll_id=policy.bankroll_id,
        version=policy.version,
        staking_mode=policy.staking_mode,
        flat_stake_pct=policy.flat_stake_pct,
        kelly_fraction=policy.kelly_fraction,
        max_ticket_pct=policy.max_ticket_pct,
        max_open_exposure_pct=policy.max_open_exposure_pct,
        max_match_pct=policy.max_match_pct,
        max_team_pct=policy.max_team_pct,
        max_league_window_pct=policy.max_league_window_pct,
        league_window_hours=policy.league_window_hours,
        max_daily_stake_pct=policy.max_daily_stake_pct,
        max_weekly_stake_pct=policy.max_weekly_stake_pct,
        max_daily_ticket_count=policy.max_daily_ticket_count,
        max_weekly_ticket_count=policy.max_weekly_ticket_count,
        accumulators_enabled=policy.accumulators_enabled,
        automation_enabled=policy.automation_enabled,
        effective_from=policy.effective_from,
        created_at=policy.created_at,
    )


async def _risk_policy_envelope(db: AsyncSession, bankroll: Bankroll) -> RiskPolicyEnvelope:
    policy = await load_active_policy(db, bankroll.id)
    state = await load_risk_state(db, bankroll.id)
    usage = await load_risk_usage(db, bankroll_id=bankroll.id)
    balance = Decimal(str(bankroll.balance))
    usage.bankroll_balance = balance
    usage.available_balance = balance
    usage.open_exposure_pct = (
        (usage.open_exposure_amount / balance).quantize(Decimal("0.000001")) if balance > 0 else None
    )
    pending = None
    if state is not None and isinstance(state.pending_policy, dict):
        pending = RiskPolicyWriteRequest.model_validate(state.pending_policy)
    pause_state = None
    if state is not None:
        pause_state = RiskPauseStateResponse(
            paused_until=state.paused_until,
            pause_reason=state.pause_reason,
            updated_at=state.updated_at,
        )
    return RiskPolicyEnvelope(
        policy=_policy_response(policy) if policy is not None else None,
        pending_policy=pending,
        pending_effective_at=state.pending_effective_at if state is not None else None,
        state=pause_state,
        usage=usage,
    )


@router.get("", response_model=list[BankrollResponse])
async def list_bankrolls(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Bankroll).where(Bankroll.user_id == user.id).order_by(Bankroll.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=BankrollResponse, status_code=201)
async def create_bankroll(
    body: BankrollCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bankroll = Bankroll(
        user_id=user.id,
        name=body.name,
        type=body.type,
        balance=body.initial_balance,
        initial_balance=body.initial_balance,
        currency=body.currency,
    )
    db.add(bankroll)
    await db.flush()
    return bankroll


@router.get("/{bankroll_id}", response_model=BankrollResponse)
async def get_bankroll(
    bankroll_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Bankroll).where(Bankroll.id == bankroll_id, Bankroll.user_id == user.id)
    result = await db.execute(stmt)
    bankroll = result.scalar_one_or_none()
    if not bankroll:
        raise HTTPException(status_code=404, detail="Bankroll not found")
    return bankroll


@router.delete("/{bankroll_id}", status_code=204)
async def delete_bankroll(
    bankroll_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Bankroll).where(Bankroll.id == bankroll_id, Bankroll.user_id == user.id)
    result = await db.execute(stmt)
    bankroll = result.scalar_one_or_none()
    if not bankroll:
        raise HTTPException(status_code=404, detail="Bankroll not found")
    await db.delete(bankroll)
    await db.flush()


@router.get("/{bankroll_id}/risk-policy", response_model=RiskPolicyEnvelope)
async def get_risk_policy(
    bankroll_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bankroll = await _owned_bankroll(db, bankroll_id, user.id)
    return await _risk_policy_envelope(db, bankroll)


@router.put("/{bankroll_id}/risk-policy", response_model=RiskPolicyEnvelope)
async def put_risk_policy(
    bankroll_id: int,
    body: RiskPolicyWriteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bankroll = await _owned_bankroll(db, bankroll_id, user.id)
    await upsert_risk_policy(db, bankroll_id=bankroll.id, user_id=user.id, body=body)
    return await _risk_policy_envelope(db, bankroll)


@router.post("/{bankroll_id}/pause", response_model=RiskPolicyEnvelope)
async def pause_risk_policy(
    bankroll_id: int,
    body: RiskPauseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bankroll = await _owned_bankroll(db, bankroll_id, user.id)
    try:
        await pause_bankroll(
            db,
            bankroll_id=bankroll.id,
            user_id=user.id,
            paused_until=body.paused_until,
            reason=body.pause_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _risk_policy_envelope(db, bankroll)


@router.get("/{bankroll_id}/accounts", response_model=list[BookmakerAccountResponse])
async def list_bookmaker_accounts(
    bankroll_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bankroll_stmt = select(Bankroll).where(Bankroll.id == bankroll_id, Bankroll.user_id == user.id)
    bankroll_result = await db.execute(bankroll_stmt)
    bankroll = bankroll_result.scalar_one_or_none()
    if not bankroll:
        raise HTTPException(status_code=404, detail="Bankroll not found")

    stmt = select(BookmakerAccount).where(BookmakerAccount.bankroll_id == bankroll_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{bankroll_id}/accounts", response_model=BookmakerAccountResponse, status_code=201)
async def create_bookmaker_account(
    bankroll_id: int,
    body: BookmakerAccountCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Bankroll).where(Bankroll.id == bankroll_id, Bankroll.user_id == user.id)
    result = await db.execute(stmt)
    bankroll = result.scalar_one_or_none()
    if not bankroll:
        raise HTTPException(status_code=404, detail="Bankroll not found")

    account = BookmakerAccount(
        bankroll_id=bankroll_id,
        bookmaker=body.bookmaker,
        account_name=body.account_name,
        balance=body.balance,
    )
    db.add(account)
    await db.flush()
    return account


@router.get("/{bankroll_id}/ledger", response_model=list[LedgerEntryResponse])
async def list_ledger(
    bankroll_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bankroll_stmt = select(Bankroll).where(Bankroll.id == bankroll_id, Bankroll.user_id == user.id)
    bankroll_result = await db.execute(bankroll_stmt)
    bankroll = bankroll_result.scalar_one_or_none()
    if not bankroll:
        raise HTTPException(status_code=404, detail="Bankroll not found")

    stmt = (
        select(LedgerEntry)
        .where(LedgerEntry.bankroll_id == bankroll_id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()
