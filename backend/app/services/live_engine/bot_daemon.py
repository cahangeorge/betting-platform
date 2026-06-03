"""Live bot daemon — orchestrates monitoring, value detection, risk management,
and entry-only execution in a continuous async loop."""
from __future__ import annotations

import asyncio
import datetime
import json
import traceback
from decimal import Decimal
from typing import Any

import redis.asyncio as redis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.models.bankroll import Bankroll
from app.models.match import Match
from app.services.exchanges.betfair import BetfairClient
from app.services.exchanges.smarkets import SmarketsClient
from app.services.live_engine.execution import ExecutionService
from app.services.live_engine.momentum import LiveMomentumScorer
from app.services.live_engine.probability_updater import LiveProbabilityUpdater
from app.services.live_engine.risk_manager import RiskManager
from app.services.live_engine.value_detector import ValueDetector
from app.services.training.trainer import FittedPredictionService


class LiveBotDaemon:
    def __init__(
        self,
        bankroll_id: str,
        kelly_fraction: float = 0.5,
        edge_threshold: float = 0.15,
        poll_interval_seconds: float = 5.0,
        paper: bool = True,
        exchange_whitelist: list[str] | None = None,
        min_odds: float = 1.5,
        max_odds: float = 20.0,
        use_contrarian: bool = True,
    ) -> None:
        self.bankroll_id = bankroll_id
        self.kelly_fraction = kelly_fraction
        self.edge_threshold = edge_threshold
        self.poll_interval = poll_interval_seconds
        self.paper = paper
        self.exchange_whitelist = exchange_whitelist or ["betfair", "smarkets"]
        self.min_odds = min_odds
        self.max_odds = max_odds
        self.use_contrarian = use_contrarian
        self.betfair = BetfairClient()
        self.smarkets = SmarketsClient()
        self.detector = ValueDetector(edge_threshold=edge_threshold)
        self.momentum_scorer = LiveMomentumScorer()
        self.prob_updater = LiveProbabilityUpdater()
        self.prediction_service = FittedPredictionService("latest")
        self._redis: redis.Redis | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        # Persistent risk manager — survives across cycles
        self._risk: RiskManager | None = None
        self.stats: dict[str, Any] = {
            "cycles": 0, "signals_found": 0, "orders_placed": 0,
            "orders_rejected": 0, "errors": 0, "last_cycle_at": None,
        }

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        try:
            await self.prediction_service.load()
        except Exception:
            pass
        while self._running:
            cycle_start = datetime.datetime.now(datetime.timezone.utc)
            try:
                await self._cycle()
            except Exception:
                self.stats["errors"] += 1
                traceback.print_exc()
            self.stats["cycles"] += 1
            self.stats["last_cycle_at"] = cycle_start.isoformat()
            elapsed = (datetime.datetime.now(datetime.timezone.utc) - cycle_start).total_seconds()
            await asyncio.sleep(max(0.0, self.poll_interval - elapsed))

    async def _cycle(self) -> None:
        async with async_session_factory() as db:
            result = await db.execute(select(Match).where(Match.status == "live"))
            matches = list(result.scalars().all())
            if not matches:
                return
            bres = await db.execute(select(Bankroll).where(Bankroll.id == self.bankroll_id))
            bankroll = bres.scalar_one_or_none()
            if not bankroll:
                return
            # Persistent risk manager — update balance, don't recreate
            if self._risk is None:
                self._risk = RiskManager(
                    bankroll_balance=bankroll.balance,
                    kelly_fraction=self.kelly_fraction,
                    max_exposure_per_match=Decimal("50.0"),
                    max_daily_loss=Decimal("200.0"),
                    max_concurrent_positions=5,
                    min_odds=self.min_odds,
                    max_odds=self.max_odds,
                )
            else:
                self._risk.update_balance(bankroll.balance)
            for match in matches:
                await self._process_match(db, match, self._risk)

    async def _process_match(
        self, db: Any, match: Any, risk: RiskManager,
    ) -> None:
        mid = str(match.id)
        elapsed = 0  # will be replaced by DB stat lookup
        momentum_diff = 0.0

        # 1. Fetch latest stat snapshot for momentum scoring
        from app.models.match import MatchStat
        stat_result = await db.execute(
            select(MatchStat).where(
                MatchStat.match_id == mid,
                MatchStat.is_deleted.is_(False),
            ).order_by(MatchStat.elapsed.desc()).limit(1)
        )
        latest_stat = stat_result.scalar_one_or_none()

        if latest_stat:
            elapsed = latest_stat.elapsed or 0
            ms = self.momentum_scorer.score_from_matchstat(mid, latest_stat)
            momentum_diff = ms.differential

        # 2. Get base model probabilities
        base_probs = {"home": 0.3333, "draw": 0.3333, "away": 0.3333}
        try:
            from app.schemas import PredictionInput
            payload = PredictionInput(
                home_team=match.home_team, away_team=match.away_team,
                league=match.league,
                match_date=datetime.datetime.now(datetime.timezone.utc),
            )
            p = await self.prediction_service.predict(payload, model_key="poisson")
            base_probs = {
                "home": float(p.home_win_prob),
                "draw": float(p.draw_prob),
                "away": float(p.away_win_prob),
            }
        except Exception:
            pass

        # 3. Update probabilities with live match context
        live_probs = self.prob_updater.update(
            base_probs=base_probs,
            home_score=match.home_score or 0,
            away_score=match.away_score or 0,
            momentum_diff=momentum_diff,
            elapsed=elapsed,
        )

        # 4. Fetch odds
        all_rows: list[dict[str, Any]] = []
        if match.betfair_market_id and "betfair" in self.exchange_whitelist:
            try:
                books = await self.betfair.list_market_book([match.betfair_market_id])
                for book in books:
                    for runner in book.get("runners", []):
                        ex = runner.get("ex", {})
                        all_rows.append({
                            "runner": str(runner.get("selectionId", "")),
                            "available_to_back": ex.get("availableToBack", [])[:3],
                            "available_to_lay": ex.get("availableToLay", [])[:3],
                            "exchange": "betfair", "match_id": mid,
                        })
            except Exception:
                pass
        if match.smarkets_market_id and "smarkets" in self.exchange_whitelist:
            try:
                smarkets_mid = match.smarkets_market_id
                quotes = await self.smarkets.list_market_quotes(smarkets_mid)
                for cid, levels in quotes.get("quotes", {}).items():
                    all_rows.append({
                        "runner": cid,
                        "available_to_back": [{"price": float(b[0]) / 100, "size": float(b[1]) / 100} for b in levels.get("bids", [])][:3],
                        "available_to_lay": [{"price": float(l[0]) / 100, "size": float(l[1]) / 100} for l in levels.get("asks", [])][:3],
                        "exchange": "smarkets", "match_id": mid,
                    })
            except Exception:
                pass

        for exchange in self.exchange_whitelist:
            exchange_rows = [r for r in all_rows if r.get("exchange") == exchange]
            if not exchange_rows:
                continue
            market_id = getattr(match, f"{exchange}_market_id", "unknown") or "unknown"
            # Standard value detection with live-adjusted probabilities
            signals = self.detector.detect(
                match_id=mid, model_probs=live_probs, live_odds_rows=exchange_rows,
                exchange=exchange, market_id=market_id,
                kelly_fraction=self.kelly_fraction, max_bet=Decimal("100.0"),
            )

            # Contrarian detection (odds >= 3.0, momentum mismatch)
            if self.use_contrarian:
                contrarian = self.detector.detect_contrarian(
                    match_id=mid, model_probs=live_probs, live_odds_rows=exchange_rows,
                    exchange=exchange, market_id=market_id,
                    min_odds=3.0, momentum_diff=momentum_diff,
                    momentum_direction="negative",
                    kelly_fraction=self.kelly_fraction, max_bet=Decimal("100.0"),
                )
                signals.extend(contrarian)
            execution = ExecutionService(db, paper=self.paper)
            for signal in signals:
                self.stats["signals_found"] += 1
                approved, reason = risk.approve(signal)
                if approved:
                    result = await execution.place_entry(signal=signal, bankroll_id=self.bankroll_id)
                    if result["status"] in ("filled", "placed"):
                        risk.record_position(signal)
                        self.stats["orders_placed"] += 1
                    else:
                        self.stats["orders_rejected"] += 1
                else:
                    self.stats["orders_rejected"] += 1
            await execution.close()

    def status(self) -> dict[str, Any]:
        return {"running": self._running, "paper": self.paper, **self.stats}
