"""Training API routes — import CSV, fit models, evaluate."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_current_user
from app.models.match import Match
from app.models.user import User
from app.services.training.trainer import ModelTrainer, fetch_training_data

router = APIRouter(prefix="/training", tags=["training"])


@router.post("/import-csv", response_model=dict[str, Any])
async def import_csv(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Import finished matches from /root/betting_platform/backend/data/historical_matches.csv
    into the match table as finished entries."""
    import csv
    import datetime
    from pathlib import Path

    csv_path = Path(__file__).resolve().parents[3] / "data" / "historical_matches.csv"
    if not csv_path.exists():
        return {"status": "error", "reason": "csv_not_found", "path": str(csv_path)}

    inserted = 0
    skipped = 0
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ext_id = f"hist-{row.get('Date', '')}-{row.get('HomeTeam', '')}-{row.get('AwayTeam', '')}"
            # Check existing
            existing = await db.execute(
                select(Match).where(Match.external_id == ext_id)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            try:
                home_score = int(row.get("FTHG", 0))
                away_score = int(row.get("FTAG", 0))
            except (ValueError, TypeError):
                skipped += 1
                continue

            match = Match(
                external_id=ext_id,
                home_team=row.get("HomeTeam", ""),
                away_team=row.get("AwayTeam", ""),
                league=row.get("League", row.get("Div", "UNKNOWN")),
                sport="football",
                kickoff_time=datetime.datetime.now(datetime.timezone.utc),
                status="finished",
                home_score=home_score,
                away_score=away_score,
            )
            db.add(match)
            inserted += 1

        await db.commit()

    return {"status": "ok", "inserted": inserted, "skipped": skipped, "path": str(csv_path)}


@router.post("/fit", response_model=dict[str, Any])
async def fit_models(
    league: str | None = None,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch training data and fit Poisson + Dixon-Coles models."""
    data = await fetch_training_data(league=league)
    if not data:
        return {"status": "error", "reason": "no_training_data", "league": league}

    trainer = ModelTrainer()
    metrics = await trainer.fit(data)
    path = await trainer.save("latest")
    return {"status": "ok", **metrics, "artifact": str(path)}


@router.post("/fit-and-eval", response_model=dict[str, Any])
async def fit_and_evaluate(
    league: str | None = None,
    holdout_ratio: float = 0.2,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Fit on a training split, evaluate calibration on hold-out."""
    from app.services.training.calibration import backtest_1x2, expected_calibration_error

    data = await fetch_training_data(league=league)
    if len(data) < 20:
        return {"status": "error", "reason": f"need >=20 matches, got {len(data)}"}

    split = int(len(data) * (1 - holdout_ratio))
    train_data = data[:split]
    test_data = data[split:]

    trainer = ModelTrainer()
    metrics = await trainer.fit(train_data)
    await trainer.save("latest")

    # Evaluate on holdout
    from app.schemas import PredictionInput
    from app.services.training.trainer import FittedPredictionService

    service = FittedPredictionService("latest")
    await service.load()

    predictions = []
    outcomes = []
    for row in test_data:
        try:
            p = await service.predict(
                PredictionInput(home_team=row["home_team"], away_team=row["away_team"], league=row.get("league", "")),
                model_key="poisson",
            )
            predictions.append({
                "home_win": float(p.home_win_prob),
                "draw": float(p.draw_prob),
                "away_win": float(p.away_win_prob),
            })
            if row["FTHG"] > row["FTAG"]:
                outcomes.append("home")
            elif row["FTHG"] == row["FTAG"]:
                outcomes.append("draw")
            else:
                outcomes.append("away")
        except Exception:
            continue

    ece = expected_calibration_error(predictions, outcomes)
    bt = backtest_1x2(predictions, outcomes)

    return {
        "status": "ok",
        "train_size": len(train_data),
        "test_size": len(test_data),
        **metrics,
        "calibration": {
            "ece_overall": round(ece, 4),
            "backtest_trades": bt["trades"],
            "backtest_win_rate": round(bt["win_rate"], 4),
            "backtest_roi": round(bt["roi"], 4),
        },
    }