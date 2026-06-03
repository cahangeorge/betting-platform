"""Backtest CLI — run the strategy against historical matches.

Usage:
  uv run python3 scripts/backtest_cli.py --stake 1000 --kelly 0.25 --edge 0.05
  uv run python3 scripts/backtest_cli.py --stake 500 --kelly 0.5 --edge 0.10 --csv data/historical_matches.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import engine
from app.models.base import metadata
from app.services.training.backtest import BacktestEngine
from app.services.training.trainer import ModelTrainer, fetch_training_data


async def run_backtest(
    initial_bankroll: float = 1000.0,
    kelly_fraction: float = 0.25,
    edge_threshold: float = 0.05,
    min_odds: float = 1.5,
    csv_path: str | None = None,
    max_matches: int | None = None,
) -> dict[str, Any]:
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    # Load training data
    data: list[dict[str, Any]] = []

    if csv_path:
        path = Path(csv_path)
        if not path.exists():
            path = Path(__file__).resolve().parents[2] / "backend" / csv_path
        if path.exists():
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        data.append({
                            "home_team": row.get("HomeTeam", ""),
                            "away_team": row.get("AwayTeam", ""),
                            "FTHG": int(row.get("FTHG", 0)),
                            "FTAG": int(row.get("FTAG", 0)),
                            "league": row.get("League", row.get("Div", "PL")),
                        })
                    except (ValueError, TypeError):
                        continue
    else:
        # Try CSV directly (load without DB)
        import csv
        found_path = None
        for p in [
            Path(__file__).resolve().parents[1] / "data" / "historical_matches.csv",
        ]:
            if p.exists():
                found_path = p
                break
        if found_path:
            with open(found_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        data.append({
                            "home_team": row.get("HomeTeam", ""),
                            "away_team": row.get("AwayTeam", ""),
                            "FTHG": int(row.get("FTHG", 0)),
                            "FTAG": int(row.get("FTAG", 0)),
                            "league": row.get("League", row.get("Div", "PL")),
                        })
                    except (ValueError, TypeError):
                        continue
        else:
            data = await fetch_training_data()

    if not data:
        return {"error": "No training data found. Import CSV or run /training/import-csv first."}

    if max_matches and max_matches < len(data):
        data = data[-max_matches:]

    print(f"  Matches loaded: {len(data)}")

    # Out-of-sample backtest: train on first 80%, test on last 20%
    split = max(10, int(len(data) * 0.8))
    train_data = data[:split]
    test_data = data[split:]
    print(f"  Train: {len(train_data)} matches, Test: {len(test_data)} matches")

    trainer = ModelTrainer()
    await trainer.fit(train_data)
    await trainer.save("latest")

    bt = BacktestEngine(
        initial_bankroll=initial_bankroll,
        kelly_fraction=kelly_fraction,
        edge_threshold=edge_threshold,
        min_odds=min_odds,
    )
    await bt.load_model()
    # Run on unseen test data only
    result = await bt.run(test_data, model_key="poisson")

    return result.full_report()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the betting strategy")
    parser.add_argument("--stake", type=float, default=1000.0, help="Starting bankroll")
    parser.add_argument("--kelly", type=float, default=0.25, help="Kelly fraction (0-1)")
    parser.add_argument("--edge", type=float, default=0.05, help="Edge threshold")
    parser.add_argument("--min-odds", type=float, default=1.5, help="Minimum odds to bet")
    parser.add_argument("--csv", type=str, default=None, help="Path to CSV with match data")
    parser.add_argument("--max", type=int, default=None, help="Max matches to backtest")
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"  BACKTEST: ${args.stake:.0f} | Kelly {args.kelly} | Edge {args.edge} | Min odds {args.min_odds}")
    print(f"{'='*70}\n")

    report = await run_backtest(
        initial_bankroll=args.stake,
        kelly_fraction=args.kelly,
        edge_threshold=args.edge,
        min_odds=args.min_odds,
        csv_path=args.csv,
        max_matches=args.max,
    )

    if "error" in report:
        print(f"  ERROR: {report['error']}")
        return

    s = report["summary"]
    print(f"  Summary:")
    print(f"    Trades:        {s['total_trades']:>4} ({s['wins']}W / {s['losses']}L)")
    print(f"    Win rate:      {s['win_rate_pct']:>6.2f}%")
    print(f"    Bankroll:      ${s['initial_bankroll']:>7.2f} → ${s['final_bankroll']:>7.2f}")
    print(f"    P&L:           ${s['total_pnl']:>+7.2f} ({s['roi_pct']:>+.2f}%)")
    print(f"    Sharpe:        {s['sharpe_ratio']:>7.4f}")
    print(f"    Max DD:        {s['max_drawdown_pct']:>6.2f}%")
    print(f"    Profit factor: {s['profit_factor']}")
    print(f"    Avg odds:      {s['avg_odds']:>5.2f}")
    print(f"    Avg edge:     {s['avg_edge']:>7.4f}")
    print()

    a = report.get("edge_analysis", {})
    print(f"  Edge analysis:")
    print(f"    Min edge:  {a.get('min_edge', 0):.4f}")
    print(f"    Max edge:  {a.get('max_edge', 0):.4f}")
    print(f"    Won avg:   {a.get('won_avg_edge', 0):.4f}")
    print(f"    Lost avg:  {a.get('lost_avg_edge', 0):.4f}")
    print()

    if report.get("league_breakdown"):
        print(f"  By league:")
        print(f"  {'League':<8} {'Trades':<8} {'Wins':<6} {'Win%':<8} {'P&L':<10} {'Avg Edge':<10}")
        print(f"  {'-'*50}")
        for league, lb in sorted(report["league_breakdown"].items()):
            print(f"  {league:<8} {lb['count']:<8} {lb['wins']:<6} {lb['win_rate']*100:<7.1f}% ${lb['total_pnl']:<+7.2f} {lb['avg_edge']:<10.4f}")

    print(f"\n{'='*70}")
    print(f"  BACKTEST COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())