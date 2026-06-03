"""Backtesting engine — replays historical matches through the full strategy pipeline.

Produces comprehensive analytics:
- P&L: total, per-trade, ROI, profit factor
- Risk: Sharpe ratio, max drawdown, Kelly curve
- Edge: distribution by bucket, hit rate by edge size
- Odds: win rate by odds range
- League: performance breakdown
- Bankroll: full equity curve
"""
from __future__ import annotations

import datetime
import math
import random
from collections import defaultdict
from decimal import Decimal
from typing import Any

from app.schemas import PredictionInput
from app.services.live_engine.value_detector import ValueDetector
from app.services.training.trainer import FittedPredictionService


# ── Helpers ─────────────────────────────────────

def _simulate_odds(true_prob: float) -> float:
    """Simulate market odds with occasional mispricing for backtesting."""
    fair = 1.0 / true_prob
    margin = 0.01
    market_odds = fair * (1.0 - margin)
    # Occasionally create edges: +noise means odds longer → implied lower → edge positive
    noise = random.choice([-0.10, -0.08, -0.05, 0.0, 0.05, 0.08, 0.12, 0.15]) * market_odds
    return round(max(1.2, market_odds + noise), 2)


# ── Models ──────────────────────────────────────

class BacktestTrade:
    """A single trade record from backtesting."""

    def __init__(self, trade_id: str, match: str, league: str, bet_on: str,
                 odds: float, stake: float, edge: float, model_prob: float,
                 implied_prob: float, actual_result: str, won: bool,
                 pnl: float, bankroll_after: float) -> None:
        self.trade_id = trade_id
        self.match = match
        self.league = league
        self.bet_on = bet_on
        self.odds = odds
        self.stake = stake
        self.edge = edge
        self.model_prob = model_prob
        self.implied_prob = implied_prob
        self.actual_result = actual_result
        self.won = won
        self.pnl = pnl
        self.bankroll_after = bankroll_after

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "match": self.match,
            "league": self.league,
            "bet_on": self.bet_on,
            "odds": self.odds,
            "stake": round(self.stake, 2),
            "edge": round(self.edge, 4),
            "model_prob": round(self.model_prob, 4),
            "implied_prob": round(self.implied_prob, 4),
            "actual_result": self.actual_result,
            "won": self.won,
            "pnl": round(self.pnl, 2),
            "bankroll_after": round(self.bankroll_after, 2),
        }


class BacktestResult:
    """Full backtest results with analytics."""

    def __init__(self, trades: list[BacktestTrade], initial_bankroll: float) -> None:
        self.trades = trades
        self.initial_bankroll = initial_bankroll
        self._compute()

    def _compute(self) -> None:
        """Compute all analytics from trade list."""
        self.total_trades = len(self.trades)
        self.wins = sum(1 for t in self.trades if t.won)
        self.losses = self.total_trades - self.wins
        self.win_rate = self.wins / self.total_trades if self.total_trades > 0 else 0.0

        self.total_pnl = sum(t.pnl for t in self.trades)
        self.gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        self.gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        self.profit_factor = self.gross_profit / self.gross_loss if self.gross_loss > 0 else float("inf")

        self.final_bankroll = self.initial_bankroll + self.total_pnl
        self.roi = self.total_pnl / self.initial_bankroll if self.initial_bankroll > 0 else 0.0

        # Average metrics
        self.avg_edge = sum(t.edge for t in self.trades) / self.total_trades if self.total_trades > 0 else 0.0
        self.avg_odds = sum(t.odds for t in self.trades) / self.total_trades if self.total_trades > 0 else 0.0
        self.avg_stake = sum(t.stake for t in self.trades) / self.total_trades if self.total_trades > 0 else 0.0
        self.avg_pnl = self.total_pnl / self.total_trades if self.total_trades > 0 else 0.0

        # Sharpe ratio (P&L-based)
        if self.total_trades > 1 and self.initial_bankroll > 0:
            returns = [t.pnl / self.initial_bankroll for t in self.trades]
            mean_r = sum(returns) / len(returns)
            var_r = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
            self.sharpe = mean_r / math.sqrt(var_r) if var_r > 0 else 0.0
        else:
            self.sharpe = 0.0

        # Max drawdown
        peak = max(self.initial_bankroll, 1.0)  # floor at 1.0 to avoid division by zero
        max_dd = 0.0
        self.equity_curve = [float(peak)]
        for t in self.trades:
            b = max(t.bankroll_after, 0.0)
            self.equity_curve.append(float(b))
            if b > peak:
                peak = b
            dd = (peak - b) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        self.max_drawdown = max_dd

        # Edge distribution
        edge_buckets = defaultdict(list)
        for t in self.trades:
            bucket = round(t.edge * 10) * 0.1  # 0.0-0.1, 0.1-0.2, etc.
            edge_buckets[bucket].append(t)
        self.edge_distribution = {
            f"{b:.1f}-{(b+0.1):.1f}": {
                "count": len(ts),
                "wins": sum(1 for t in ts if t.won),
                "win_rate": sum(1 for t in ts if t.won) / len(ts) if ts else 0,
                "avg_pnl": round(sum(t.pnl for t in ts) / len(ts), 2),
            }
            for b, ts in sorted(edge_buckets.items())
        }

        # Odds bucket win rates
        odds_buckets = defaultdict(list)
        for t in self.trades:
            bucket = f"{t.odds:.0f}-{(int(t.odds)+1)}" if t.odds < 6 else "6.0+"
            key = f"<{2}" if t.odds < 2 else f"{2}-{3}" if t.odds < 3 else f"{3}-{5}" if t.odds < 5 else "5+"
            odds_buckets[key].append(t)
        self.odds_win_rates = {
            k: {
                "count": len(ts),
                "wins": sum(1 for t in ts if t.won),
                "win_rate": sum(1 for t in ts if t.won) / len(ts) if ts else 0,
                "avg_pnl": round(sum(t.pnl for t in ts) / len(ts), 2),
            }
            for k, ts in sorted(odds_buckets.items())
        }

        # League breakdown
        leagues = defaultdict(list)
        for t in self.trades:
            leagues[t.league].append(t)
        self.league_breakdown = {
            k: {
                "count": len(ts),
                "wins": sum(1 for t in ts if t.won),
                "win_rate": round(sum(1 for t in ts if t.won) / len(ts), 4) if ts else 0,
                "total_pnl": round(sum(t.pnl for t in ts), 2),
                "avg_edge": round(sum(t.edge for t in ts) / len(ts), 4) if ts else 0,
            }
            for k, ts in sorted(leagues.items())
        }

        # Edge vs outcome analysis
        won_edges = [t.edge for t in self.trades if t.won]
        lost_edges = [t.edge for t in self.trades if not t.won]
        self.edge_analysis = {
            "won_avg_edge": round(sum(won_edges) / len(won_edges), 4) if won_edges else 0,
            "lost_avg_edge": round(sum(lost_edges) / len(lost_edges), 4) if lost_edges else 0,
            "min_edge": round(min(t.edge for t in self.trades), 4) if self.trades else 0,
            "max_edge": round(max(t.edge for t in self.trades), 4) if self.trades else 0,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate_pct": round(self.win_rate * 100, 2),
            "initial_bankroll": round(self.initial_bankroll, 2),
            "final_bankroll": round(self.final_bankroll, 2),
            "total_pnl": round(self.total_pnl, 2),
            "roi_pct": round(self.roi * 100, 2),
            "profit_factor": round(self.profit_factor, 2) if self.profit_factor != float("inf") else "inf",
            "sharpe_ratio": round(self.sharpe, 4),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "avg_edge": round(self.avg_edge, 4),
            "avg_odds": round(self.avg_odds, 2),
            "avg_stake": round(self.avg_stake, 2),
            "avg_pnl": round(self.avg_pnl, 2),
        }

    def full_report(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "edge_distribution": self.edge_distribution,
            "odds_win_rates": self.odds_win_rates,
            "league_breakdown": self.league_breakdown,
            "edge_analysis": self.edge_analysis,
            "equity_curve_points": len(self.equity_curve),
            "recent_trades": [t.to_dict() for t in self.trades[-20:]],
        }


class BacktestEngine:
    """Run a full backtest of the betting strategy over historical matches."""

    def __init__(
        self,
        initial_bankroll: float = 1000.0,
        kelly_fraction: float = 0.25,
        edge_threshold: float = 0.05,
        min_odds: float = 1.5,
        max_odds: float = 20.0,
        use_real_odds: bool = False,
        seed: int = 42,
    ) -> None:
        self.initial_bankroll = initial_bankroll
        self.kelly_fraction = kelly_fraction
        self.edge_threshold = edge_threshold
        self.min_odds = min_odds
        self.max_odds = max_odds
        self.use_real_odds = use_real_odds
        random.seed(seed)

        self.detector = ValueDetector(edge_threshold=edge_threshold)
        self.prediction_service = FittedPredictionService("latest")

    async def load_model(self) -> None:
        await self.prediction_service.load()

    async def run(
        self,
        matches: list[dict[str, Any]],
        model_key: str = "poisson",
    ) -> BacktestResult:
        """Run backtest over a list of match dicts.

        Each match must have:
          home_team, away_team, FTHG, FTAG, league
        Optional:
          odds_home, odds_draw, odds_away (pre-match market odds)
        """
        trades: list[BacktestTrade] = []
        bankroll = self.initial_bankroll

        for idx, row in enumerate(matches):
            home = row["home_team"]
            away = row["away_team"]
            league = row.get("league", "PL")

            actual_result = (
                "home" if row["FTHG"] > row["FTAG"]
                else "away" if row["FTAG"] > row["FTHG"]
                else "draw"
            )

            # Predict
            from app.schemas import PredictionInput
            try:
                pred = await self.prediction_service.predict(
                    PredictionInput(
                        home_team=home, away_team=away, league=league,
                        match_date=datetime.datetime.now(datetime.timezone.utc),
                    ),
                    model_key=model_key,
                )
                model_probs = {
                    "home": float(pred.home_win_prob),
                    "draw": float(pred.draw_prob),
                    "away": float(pred.away_win_prob),
                }
            except Exception:
                continue

            # Build odds rows
            live_odds_rows = []
            for runner_key in ["home", "draw", "away"]:
                prob = model_probs.get(runner_key, 0.3333)
                if prob > 0.01:
                    if self.use_real_odds:
                        odds = row.get(f"odds_{runner_key}", 0.0) or _simulate_odds(prob)
                    else:
                        odds = _simulate_odds(prob)
                    size = random.uniform(100, 1000) if not self.use_real_odds else 500
                    live_odds_rows.append({
                        "runner": runner_key,
                        "available_to_back": [{"price": odds, "size": size}],
                        "available_to_lay": [{"price": odds + 0.05, "size": size}],
                    })

            match_id = f"bt-{idx}"
            signals = self.detector.detect(
                match_id=match_id,
                model_probs=model_probs,
                live_odds_rows=live_odds_rows,
                exchange="backtest",
                market_id=match_id,
                kelly_fraction=self.kelly_fraction,
                max_bet=Decimal(str(bankroll * 0.1)),
            )

            if not signals:
                continue

            # Take best signal by edge
            best = max(signals, key=lambda s: s.edge)

            # Kelly stake
            stake = best.recommended_stake
            if stake < Decimal("0.01"):
                continue
            stake_float = float(stake)
            if stake_float > bankroll * 0.5:
                stake_float = bankroll * 0.5
                stake = Decimal(str(stake_float))

            # Settle
            won = best.runner == actual_result
            if won:
                pnl = stake_float * (best.odds - 1.0)
            else:
                pnl = -stake_float

            bankroll += pnl

            trade = BacktestTrade(
                trade_id=f"BT-{idx}",
                match=f"{home} vs {away}",
                league=league,
                bet_on=best.runner,
                odds=best.odds,
                stake=stake_float,
                edge=best.edge,
                model_prob=best.model_prob,
                implied_prob=best.implied_prob,
                actual_result=actual_result,
                won=won,
                pnl=pnl,
                bankroll_after=bankroll,
            )
            trades.append(trade)

        return BacktestResult(trades, self.initial_bankroll)