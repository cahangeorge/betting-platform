"""Execution service — entry-only BET placement."""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.bankroll import Bankroll
from app.models.live_engine import TradingPosition
from app.services.exchanges.betfair import BetfairClient
from app.services.exchanges.smarkets import SmarketsClient
from app.services.live_engine.value_detector import ValueSignal


class ExecutionService:
    def __init__(self, db: AsyncSession, paper: bool = True) -> None:
        self.db = db
        self.paper = paper
        self.betfair = BetfairClient()
        self.smarkets = SmarketsClient()

    async def close(self) -> None:
        await self.betfair.close()
        await self.smarkets.close()

    async def place_entry(self, signal: ValueSignal, bankroll_id: str) -> dict[str, Any]:
        stake = signal.recommended_stake
        position = TradingPosition(
            bankroll_id=bankroll_id,
            match_id=signal.match_id,
            market_id=signal.market_id, runner_id=0, side="BACK",
            status="open", requested_odds=signal.odds, requested_stake=stake,
            average_price_matched=None, size_matched=None, size_remaining=stake,
            betfair_bet_id=None, persistence="LAPSE" if self.paper else "PERSIST",
            model_prob_at_entry=signal.model_prob, implied_prob_at_entry=signal.implied_prob,
            edge_at_entry=signal.edge,
            entry_time=datetime.datetime.now(datetime.timezone.utc),
        )
        if self.paper:
            position.status = "filled"
            position.average_price_matched = signal.odds
            position.size_matched = stake
            position.size_remaining = Decimal("0")
            position.matched_time = datetime.datetime.now(datetime.timezone.utc)
            position.betfair_bet_id = f"paper-{datetime.datetime.now(datetime.timezone.utc).timestamp()}"
            self.db.add(position)
            await self.db.commit()
            await self._debit_bankroll(bankroll_id, stake)
            return {"status": "filled", "paper": True, "position_id": str(position.id)}
        return {"status": "paper_only", "note": "real mode not wired"}

    async def _debit_bankroll(self, bankroll_id: str, amount: Decimal) -> None:
        result = await self.db.execute(select(Bankroll).where(Bankroll.id == bankroll_id))
        b = result.scalar_one_or_none()
        if b:
            b.balance -= amount
            await self.db.commit()

    async def settle_paper_position(self, position_id: str, result: str,
                                    final_odds: float | None = None,
                                    pnl: Decimal | None = None) -> dict[str, Any]:
        res = await self.db.execute(select(TradingPosition).where(TradingPosition.id == position_id))
        pos = res.scalar_one_or_none()
        if not pos:
            return {"status": "error", "reason": "position_not_found"}
        pos.status = "settled"
        pos.final_result = result
        pos.settled_time = datetime.datetime.now(datetime.timezone.utc)
        if pnl is None and pos.average_price_matched and pos.size_matched:
            odds = Decimal(str(pos.average_price_matched))
            pnl = pos.size_matched * (odds - Decimal("1")) if result == "won" else (-pos.size_matched if result == "lost" else Decimal("0"))
        pos.profit_loss = pnl
        await self.db.commit()
        if pnl and pnl != Decimal("0"):
            await self._debit_bankroll(str(pos.bankroll_id), -pnl)
        return {"status": "settled", "position_id": position_id, "result": result, "pnl": float(pnl) if pnl else 0.0}