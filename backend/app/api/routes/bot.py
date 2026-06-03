"""Live bot API routes."""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_current_user
from app.models.bankroll import Bankroll
from app.models.live_engine import TradingPosition
from app.models.user import User
from app.services.live_engine.bot_daemon import LiveBotDaemon
from app.services.live_engine.execution import ExecutionService
from app.schemas import BotStartIn, BotStatusOut, TradeLogOut, PaperSettleIn

router = APIRouter(prefix="/bot", tags=["bot"])

_bot_registry: dict[str, LiveBotDaemon] = {}


@router.post("/start", response_model=dict[str, Any])
async def bot_start(
    payload: BotStartIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(
        select(Bankroll).where(Bankroll.id == payload.bankroll_id, Bankroll.user_id == current_user.id)
    )
    bankroll = result.scalar_one_or_none()
    if not bankroll:
        raise HTTPException(status_code=404, detail="Bankroll not found")
    key = str(bankroll.id)
    if key in _bot_registry and _bot_registry[key]._running:
        return {"status": "already_running", "bankroll_id": key}
    daemon = LiveBotDaemon(
        bankroll_id=key,
        kelly_fraction=payload.kelly_fraction,
        edge_threshold=payload.edge_threshold,
        poll_interval_seconds=payload.poll_interval_seconds,
        paper=payload.paper,
        exchange_whitelist=payload.exchange_whitelist,
        min_odds=payload.min_odds,
        max_odds=payload.max_odds,
    )
    daemon.start()
    _bot_registry[key] = daemon
    return {"status": "started", "bankroll_id": key, "paper": payload.paper}


@router.post("/stop", response_model=dict[str, Any])
async def bot_stop(
    bankroll_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    daemon = _bot_registry.get(bankroll_id)
    if not daemon:
        raise HTTPException(status_code=404, detail="Bot not running")
    await daemon.stop()
    _bot_registry.pop(bankroll_id, None)
    return {"status": "stopped", "bankroll_id": bankroll_id}


@router.get("/status", response_model=BotStatusOut)
async def bot_status(bankroll_id: str, current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    daemon = _bot_registry.get(bankroll_id)
    if not daemon:
        return {"running": False, "paper": True, "cycles": 0, "signals_found": 0, "orders_placed": 0, "orders_rejected": 0, "errors": 0, "last_cycle_at": None}
    return daemon.status()


@router.get("/trades", response_model=list[TradeLogOut])
async def list_trades(
    bankroll_id: str, status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TradingPosition]:
    query = select(TradingPosition).where(TradingPosition.bankroll_id == bankroll_id)
    if status:
        query = query.where(TradingPosition.status == status)
    query = query.order_by(TradingPosition.entry_time.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/paper/settle", response_model=dict[str, Any])
async def paper_settle(
    payload: PaperSettleIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    execution = ExecutionService(db, paper=True)
    return await execution.settle_paper_position(
        position_id=payload.position_id, result=payload.result,
        final_odds=payload.final_odds, pnl=payload.pnl,
    )