"""Execution service — entry-only bet placement on Betfair or Matchbook."""
from __future__ import annotations

import datetime
import math
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.bankroll import Bankroll
from app.models.live_engine import TradingPosition
from app.services.exchanges.betfair import BetfairClient
from app.services.exchanges.matchbook import MatchbookClient
from app.services.exchanges.smarkets import SmarketsClient
from app.services.live_engine.value_detector import ValueSignal


class ExecutionService:
    """Entry-only bet execution.

    Modes:
      paper=True: simulated fill at requested odds, no real API calls
      paper=False + exchange='betfair': real Betfair API
      paper=False + exchange='matchbook': real Matchbook API (free tier)
    """

    def __init__(self, db: AsyncSession, paper: bool = True) -> None:
        self.db = db
        self.paper = paper
        self.betfair = BetfairClient()
        self.matchbook = MatchbookClient()
        self.smarkets = SmarketsClient()

    async def close(self) -> None:
        await self.betfair.close()
        await self.matchbook.close()
        await self.smarkets.close()

    async def place_entry(self, signal: ValueSignal, bankroll_id: str) -> dict[str, Any]:
        """Place an entry BACK bet.

        signal.exchange determines which exchange to use.
        """
        stake = signal.recommended_stake
        exchange = signal.exchange.lower()

        # Common position fields
        position = TradingPosition(
            bankroll_id=bankroll_id,
            match_id=signal.match_id,
            market_id=signal.market_id,
            runner_id=0,
            side="BACK",
            status="open",
            requested_odds=signal.odds,
            requested_stake=stake,
            average_price_matched=None,
            size_matched=None,
            size_remaining=stake,
            betfair_bet_id=None,
            persistence="LAPSE" if self.paper else "PERSIST",
            model_prob_at_entry=signal.model_prob,
            implied_prob_at_entry=signal.implied_prob,
            edge_at_entry=signal.edge,
            entry_time=datetime.datetime.now(datetime.timezone.utc),
        )

        # ── PAPER MODE (default) ──
        if self.paper:
            return await self._fill_paper(position, stake, signal)

        # ── REAL MODE ──
        if exchange == "betfair":
            return await self._place_betfair(position, signal, stake)
        elif exchange == "matchbook":
            return await self._place_matchbook(position, signal, stake)
        else:
            return {"status": "error", "reason": f"unsupported_exchange:{exchange}"}

    # ── Paper mode ─────────────────────────────────

    async def _fill_paper(
        self, position: TradingPosition, stake: Decimal, signal: ValueSignal,
    ) -> dict[str, Any]:
        position.status = "filled"
        position.average_price_matched = signal.odds
        position.size_matched = stake
        position.size_remaining = Decimal("0")
        position.matched_time = datetime.datetime.now(datetime.timezone.utc)
        position.betfair_bet_id = f"paper-{datetime.datetime.now(datetime.timezone.utc).timestamp()}"
        self.db.add(position)
        await self.db.commit()
        await self._debit_bankroll(str(position.bankroll_id), stake)
        return {"status": "filled", "paper": True, "position_id": str(position.id)}

    # ── Betfair real mode ──────────────────────────

    async def _place_betfair(
        self, position: TradingPosition, signal: ValueSignal, stake: Decimal,
    ) -> dict[str, Any]:
        try:
            # Auto-login if no session token
            if not self.betfair.session_token:
                await self.betfair.login()

            # If market_id has a dot it's a Betfair market ID (e.g. "1.234567")
            market_id = signal.market_id
            selection_id = int(signal.runner) if signal.runner.isdigit() else 0
            if selection_id == 0:
                return {"status": "error", "reason": "invalid_runner_id"}

            result = await self.betfair.place_orders(market_id, [{
                "orderType": "LIMIT",
                "selectionId": selection_id,
                "side": "BACK",
                "limitOrder": {
                    "size": float(stake),
                    "price": round(signal.odds, 2),
                    "persistenceType": "PERSIST",
                },
            }])
            status = result.get("status", "UNKNOWN")
            if status == "SUCCESS":
                bet_id = result.get("instructionReports", [{}])[0].get("betId", "")
                position.betfair_bet_id = bet_id
                self.db.add(position)
                await self.db.commit()
                return {"status": "placed", "exchange": "betfair", "bet_id": bet_id, "position_id": str(position.id)}
            return {"status": "error", "reason": f"betfair_rejected:{status}"}
        except Exception as e:
            return {"status": "error", "reason": f"betfair_exception:{e}"}

    # ── Matchbook real mode (free tier) ─────────────

    async def _place_matchbook(
        self, position: TradingPosition, signal: ValueSignal, stake: Decimal,
    ) -> dict[str, Any]:
        try:
            if not self.matchbook.session_token:
                await self.matchbook.login()

            market_id = int(float(signal.market_id)) if signal.market_id.replace(".", "").isdigit() else 0
            runner_id = int(signal.runner) if signal.runner.isdigit() else 0
            if market_id == 0 or runner_id == 0:
                return {"status": "error", "reason": "invalid_market_or_runner_id"}

            result = await self.matchbook.place_bet(
                market_id=market_id,
                runner_id=runner_id,
                side="back",
                odds=signal.odds,
                stake=float(stake),
            )
            bet_id = str(result.get("id", ""))
            position.betfair_bet_id = bet_id
            self.db.add(position)
            await self.db.commit()
            return {"status": "placed", "exchange": "matchbook", "bet_id": bet_id, "position_id": str(position.id)}
        except Exception as e:
            return {"status": "error", "reason": f"matchbook_exception:{e}"}

    # ── Bankroll management ────────────────────────

    async def _debit_bankroll(self, bankroll_id: str, amount: Decimal) -> None:
        result = await self.db.execute(select(Bankroll).where(Bankroll.id == bankroll_id))
        b = result.scalar_one_or_none()
        if b:
            b.balance -= amount
            await self.db.commit()

    async def settle_paper_position(
        self, position_id: str, result: str,
        final_odds: float | None = None, pnl: Decimal | None = None,
    ) -> dict[str, Any]:
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