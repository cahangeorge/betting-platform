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

router = APIRouter()


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
