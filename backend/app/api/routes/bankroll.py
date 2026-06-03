"""Bankroll CRUD routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_current_user
from app.models.bankroll import Bankroll
from app.models.user import User
from app.schemas import BankrollCreate, BankrollOut

router = APIRouter(prefix="/bankroll", tags=["bankroll"])


@router.post("", response_model=BankrollOut, status_code=201)
async def create_bankroll(
    payload: BankrollCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Bankroll:
    bankroll = Bankroll(
        user_id=current_user.id,
        name=payload.name,
        currency=payload.currency,
    )
    db.add(bankroll)
    await db.commit()
    return bankroll


@router.get("", response_model=list[BankrollOut])
async def list_bankrolls(
    is_active: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Bankroll]:
    result = await db.execute(
        select(Bankroll).where(Bankroll.user_id == current_user.id, Bankroll.is_active == is_active)
    )
    return list(result.scalars().all())


@router.get("/{bankroll_id}", response_model=BankrollOut)
async def get_bankroll(
    bankroll_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Bankroll:
    result = await db.execute(
        select(Bankroll).where(Bankroll.id == bankroll_id, Bankroll.user_id == current_user.id)
    )
    b = result.scalar_one_or_none()
    if not b:
        raise HTTPException(status_code=404, detail="Bankroll not found")
    return b