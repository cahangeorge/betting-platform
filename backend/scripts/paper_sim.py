"""Paper trading simulator — replays historical matches through the full betting pipeline.

Usage:
  uv run python3 scripts/paper_sim.py --matches 50 --stake 500

Simulates entry-only trading across all 60 historical matches, tracking:
  - Trades placed, win rate, ROI
  - Kelly stake sizing
  - Edge distribution
  - Bankroll curve
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import random
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

# Ensure we can import from app
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import async_session_factory, engine
from app.models.base import metadata
from app.models.bankroll import Bankroll
from app.models.live_engine import TradingPosition
from app.models.match import Match
from app.models.user import User
from app.core.security import hash_password
from app.services.live_engine.value_detector import ValueSignal, ValueDetector
from app.services.live_engine.risk_manager import RiskManager
from app.services.training.trainer import FittedPredictionService, ModelTrainer, fetch_training_data


def _league_base_prob(league: str) -> dict[str, float]:
    """League-adjusted base probabilities."""
    probs = {
        "PL": {"home": 0.45, "draw": 0.26, "away": 0.29},
        "LL": {"home": 0.48, "draw": 0.25, "away": 0.27},
        "BL": {"home": 0.46, "draw": 0.24, "away": 0.30},
        "SA": {"home": 0.44, "draw": 0.27, "away": 0.29},
        "L1": {"home": 0.43, "draw": 0.28, "away": 0.29},
    }
    return probs.get(league, {"home": 0.45, "draw": 0.26, "away": 0.29})


def _simulate_odds(
    true_prob: float, margin: float = 0.01
) -> float:
    """Simulate market odds for a team.

    Fair odds = 1/true_prob. Market adds margin and occasionally misprices.
    To create edge: sometimes the market prices a runner too HIGH
    (odds too long → implied too low → positive edge for back bet).
    """
    fair = 1.0 / true_prob
    market_odds = fair * (1.0 - margin)
    # Simulate market mispricing: heavy tails for occasional value
    # Negative = market prices too short (no edge)
    # Positive = market prices too long (edge for backer!)
    noise_factor = random.choice([-0.10, -0.08, -0.05, 0.0, 0.05, 0.08, 0.12, 0.15, 0.20])
    noise = noise_factor * market_odds
    return round(max(1.2, market_odds + noise), 2)


async def run_simulation(
    bankroll_seed: float = 500.0,
    kelly_fraction: float = 0.5,
    edge_threshold: float = 0.15,
    min_odds: float = 1.5,
    max_odds: float = 20.0,
    max_trades: int | None = None,
) -> dict[str, Any]:
    """Run a full paper trading simulation against historical matches."""

    # 1. Set up DB with test data
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    async with async_session_factory() as db:
        # Check if we already have a sim user/bankroll
        from sqlalchemy import select
        result = await db.execute(
            select(User).where(User.email == "sim@papertrade.dev")
        )
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                email="sim@papertrade.dev",
                password_hash=hash_password("sim123"),
                is_superuser=True,
            )
            db.add(user)
            await db.flush()

        result = await db.execute(
            select(Bankroll).where(Bankroll.user_id == user.id, Bankroll.name == "Paper Sim")
        )
        bankroll = result.scalar_one_or_none()
        if not bankroll:
            bid = Bankroll(
                user_id=user.id,
                name="Paper Sim",
                type="paper",
                start_balance=bankroll_seed,
                balance=bankroll_seed,
                kelly_fraction=kelly_fraction,
            )
            db.add(bid)
            await db.commit()
            bankroll_id = str(bid.id)
        else:
            bankroll_id = str(bankroll.id)
            bankroll.balance = Decimal(str(bankroll_seed))
            await db.commit()

        # 2. Fetch training data from match table or CSV
        from app.services.training.trainer import fetch_training_data
        data = await fetch_training_data()
        if not data:
            # Auto-import CSV
            import csv
            csv_path = Path(__file__).resolve().parents[1] / "data" / "historical_matches.csv"
            if csv_path.exists():
                print(f"  Auto-importing from {csv_path}...")
                with open(csv_path, newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        ext_id = f"sim-{row.get('Date','')}-{row.get('HomeTeam','')}-{row.get('AwayTeam','')}"
                        try:
                            hs = int(row.get("FTHG", 0))
                            as_ = int(row.get("FTAG", 0))
                        except (ValueError, TypeError):
                            continue
                        db.add(Match(
                            external_id=ext_id,
                            home_team=row.get("HomeTeam", ""),
                            away_team=row.get("AwayTeam", ""),
                            league=row.get("League", row.get("Div", "PL")),
                            sport="football",
                            kickoff_time=datetime.datetime.now(datetime.timezone.utc),
                            status="finished",
                            home_score=hs,
                            away_score=as_,
                        ))
                    await db.commit()
                data = await fetch_training_data()

        if not data:
            return {"status": "error", "reason": "No training data available"}

        # 3. Fit model
        trainer = ModelTrainer()
        await trainer.fit(data)
        await trainer.save("latest")

        # 4. Run prediction service
        service = FittedPredictionService("latest")
        await service.load()

        # 5. Simulate trading on each match
        detector = ValueDetector(edge_threshold=edge_threshold)
        risk = RiskManager(
            bankroll_balance=Decimal(str(bankroll_seed)),
            kelly_fraction=kelly_fraction,
            max_exposure_per_match=Decimal("50.0"),
            max_daily_loss=Decimal("500.0"),
            max_concurrent_positions=10,
            min_odds=min_odds,
            max_odds=max_odds,
        )

        trades = []
        matches_processed = 0
        matches_skipped = 0

        for row in data[:max_trades] if max_trades else data:
            matches_processed += 1
            home = row["home_team"]
            away = row["away_team"]
            league = row.get("league", "PL")

            # Check if this is a known/expected match for stopping
            actual_fthg = row["FTHG"]
            actual_ftag = row["FTAG"]
            actual_result = (
                "home" if actual_fthg > actual_ftag
                else "away" if actual_ftag > actual_fthg
                else "draw"
            )

            # Get model prediction
            from app.schemas import PredictionInput
            try:
                pred = await service.predict(
                    PredictionInput(
                        home_team=home, away_team=away, league=league,
                        match_date=datetime.datetime.now(datetime.timezone.utc),
                    ),
                    model_key="poisson",
                )
                model_probs = {
                    "home": float(pred.home_win_prob),
                    "draw": float(pred.draw_prob),
                    "away": float(pred.away_win_prob),
                }
            except Exception:
                model_probs = _league_base_prob(league)

            # Simulate live odds for each runner
            live_odds_rows = []
            for runner_key in ["home", "draw", "away"]:
                prob = model_probs.get(runner_key, 0.3333)
                if prob > 0.01:
                    odds = _simulate_odds(prob)
                    # Slight price variation between runners
                    size = random.uniform(50, 500)
                    live_odds_rows.append({
                        "runner": runner_key,
                        "available_to_back": [{"price": odds, "size": size}],
                        "available_to_lay": [{"price": odds + 0.05, "size": size}],
                    })

            # Detect value
            match_id = f"sim-{home}-{away}".replace(" ", "-")
            signals = detector.detect(
                match_id=match_id,
                model_probs=model_probs,
                live_odds_rows=live_odds_rows,
                exchange="paper",
                market_id=match_id,
                kelly_fraction=kelly_fraction,
                max_bet=Decimal("50.0"),
            )

            if not signals:
                matches_skipped += 1
                continue

            # Sort by edge descending and take the best signal
            best = max(signals, key=lambda s: s.edge)
            approved, reason = risk.approve(best)
            if not approved:
                matches_skipped += 1
                continue

            # Execute paper trade
            stake = best.recommended_stake
            if stake < Decimal("0.01"):
                matches_skipped += 1
                continue

            risk.record_position(best)

            # Determine outcome
            runner = best.runner
            won = runner == actual_result

            if won:
                pnl = stake * (Decimal(str(best.odds)) - Decimal("1"))
                risk.bankroll_balance += pnl
            else:
                pnl = -stake
                risk.bankroll_balance += pnl

            risk.daily_pnl += pnl

            trades.append({
                "match": f"{home} vs {away}",
                "league": league,
                "bet_on": runner,
                "actual": actual_result,
                "odds": best.odds,
                "model_prob": round(best.model_prob, 4),
                "implied_prob": round(best.implied_prob, 4),
                "edge": round(best.edge, 4),
                "stake": float(stake),
                "pnl": float(pnl),
                "won": won,
                "bankroll_after": float(risk.bankroll_balance),
            })

        # 6. Calculate final metrics
        total_trades = len(trades)
        wins = sum(1 for t in trades if t["won"])
        losses = total_trades - wins
        total_pnl = sum(t["pnl"] for t in trades)
        roi = total_pnl / bankroll_seed * 100 if bankroll_seed > 0 else 0
        win_rate = wins / total_trades * 100 if total_trades > 0 else 0
        avg_edge = sum(t["edge"] for t in trades) / total_trades if total_trades > 0 else 0
        avg_odds = sum(t["odds"] for t in trades) / total_trades if total_trades > 0 else 0

        final_balance = float(risk.bankroll_balance)

        return {
            "status": "ok",
            "simulation": {
                "seed_bankroll": bankroll_seed,
                "final_balance": round(final_balance, 2),
                "roi_pct": round(roi, 2),
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "win_rate_pct": round(win_rate, 2),
                "avg_edge": round(avg_edge, 4),
                "avg_odds": round(avg_odds, 2),
                "matches_processed": matches_processed,
                "matches_skipped": matches_skipped,
                "kelly_fraction": kelly_fraction,
                "edge_threshold": edge_threshold,
            },
            "trades": trades[-20:] if total_trades > 20 else trades,
            "top_trades": sorted(trades, key=lambda t: abs(t["pnl"]), reverse=True)[:5],
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Paper trading simulation")
    parser.add_argument("--stake", type=float, default=500.0, help="Starting bankroll")
    parser.add_argument("--kelly", type=float, default=0.5, help="Kelly fraction (0-1)")
    parser.add_argument("--edge", type=float, default=0.15, help="Edge threshold")
    parser.add_argument("--matches", type=int, default=None, help="Max trades to place")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  PAPER TRADING SIMULATION")
    print(f"  Bankroll: ${args.stake:.2f} | Kelly: {args.kelly} | Edge threshold: {args.edge}")
    print(f"{'='*60}\n")

    result = await run_simulation(
        bankroll_seed=args.stake,
        kelly_fraction=args.kelly,
        edge_threshold=args.edge,
        max_trades=args.matches,
    )

    if result["status"] == "error":
        print(f"ERROR: {result['reason']}")
        return

    sim = result["simulation"]
    print(f"  Results:")
    print(f"    Final balance:    ${sim['final_balance']:>8.2f}")
    print(f"    ROI:              {sim['roi_pct']:>+7.2f}%")
    print(f"    Trades:           {sim['total_trades']:>4}")
    print(f"    Win rate:         {sim['win_rate_pct']:>5.1f}%")
    print(f"    Avg edge:         {sim['avg_edge']:>7.4f}")
    print(f"    Avg odds:         {sim['avg_odds']:>5.2f}")
    print(f"    Matches skipped:  {sim['matches_skipped']:>4}")
    print()

    if result["trades"]:
        print(f"  Last {len(result['trades'])} trades:")
        print(f"  {'Match':<30} {'Bet':<6} {'Actual':<8} {'Odds':<6} {'Edge':<7} {'P&L':<8}")
        print(f"  {'-'*65}")
        for t in result["trades"][-10:]:
            won_str = "WON" if t["won"] else "LOST"
            print(f"  {t['match']:<30} {t['bet_on']:<6} {won_str:<8} {t['odds']:<6} {t['edge']:<7.3f} {t['pnl']:<+8.2f}")

    print(f"\n{'='*60}")
    print(f"  SIMULATION COMPLETE")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())