import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match
from app.models.prediction import EnsemblePrediction, ModelPrediction, PredictionRun
from app.services.prediction_engine import execute_single_model_run


async def compute_brier_weights(
    db: AsyncSession,
    model_keys: list[str],
    league: str,
) -> dict[str, float]:
    weights: dict[str, float] = {}
    all_uniform = True

    stmt = (
        select(ModelPrediction, Match.home_score, Match.away_score)
        .join(PredictionRun, ModelPrediction.run_id == PredictionRun.id)
        .join(Match, ModelPrediction.match_id == Match.id)
        .where(
            ModelPrediction.market == "1x2",
            PredictionRun.status == "completed",
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
            Match.competition.ilike(f"%{league}%"),
        )
        .order_by(ModelPrediction.id.desc())
        .limit(600 * len(model_keys))
    )
    result = await db.execute(stmt)
    rows = result.all()

    by_model: dict[str, list[tuple]] = {}
    for mp, hs, aw in rows:
        by_model.setdefault(mp.model_type, []).append((mp, hs, aw))

    for mk in model_keys:
        model_rows = by_model.get(mk, [])
        by_match: dict[int, dict] = {}
        for mp, hs, aw in model_rows:
            if mp.match_id not in by_match:
                by_match[mp.match_id] = {"home": None, "draw": None, "away": None, "hs": hs, "as": aw}
            by_match[mp.match_id]["home"] = mp.home_prob
            by_match[mp.match_id]["draw"] = mp.draw_prob
            by_match[mp.match_id]["away"] = mp.away_prob

        sum_brier = 0.0
        count = 0
        for v in by_match.values():
            if v["home"] is None or v["draw"] is None or v["away"] is None:
                continue
            hs, aw = int(v["hs"]), int(v["as"])
            actual = [1.0, 0.0, 0.0] if hs > aw else ([0.0, 1.0, 0.0] if hs == aw else [0.0, 0.0, 1.0])
            brier = (v["home"] - actual[0]) ** 2 + (v["draw"] - actual[1]) ** 2 + (v["away"] - actual[2]) ** 2
            sum_brier += brier
            count += 1

        if count >= 10:
            mean_brier = sum_brier / count
            weights[mk] = 1.0 / (mean_brier + 1e-3)
            all_uniform = False
        else:
            weights[mk] = 1.0

    if all_uniform:
        for mk in model_keys:
            weights[mk] = 1.0

    total = sum(weights.values())
    if total > 0:
        for k in weights:
            weights[k] /= total
    return weights


async def run_ensemble_prediction(
    db: AsyncSession,
    league: str,
    model_keys: list[str],
    markets: list[str] | None = None,
    weighting: str = "uniform",
    sport: str = "football",
    training_limit: int = 380,
    target_limit: int = 50,
    target_mode: str = "future",
    max_goals: int = 10,
    user_id: int | None = None,
) -> dict:
    if markets is None:
        markets = ["1x2"]

    weights: dict[str, float]
    if weighting == "brier":
        weights = await compute_brier_weights(db, model_keys, league)
    else:
        weights = {mk: 1.0 / len(model_keys) for mk in model_keys}

    run = PredictionRun(
        user_id=user_id,
        model_type="ensemble",
        ensemble=True,
        status="running",
        matches_count=0,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    try:
        member_summaries: dict[str, dict] = {}
        for mk in model_keys:
            summary = await execute_single_model_run(
                db,
                run.id,
                mk,
                league,
                markets,
                sport,
                training_limit,
                target_limit,
                target_mode,
                max_goals,
            )
            member_summaries[mk] = summary

        stmt = select(ModelPrediction).where(ModelPrediction.run_id == run.id)
        result = await db.execute(stmt)
        member_rows = result.scalars().all()

        acc: dict[str, dict] = {}
        for r in member_rows:
            w = weights.get(r.model_type, 0)
            if w <= 0:
                continue
            key = f"{r.match_id}|{r.market}"
            if key not in acc:
                acc[key] = {
                    "sum_w": 0.0,
                    "match_id": r.match_id,
                    "market": r.market,
                    "home_prob": 0.0,
                    "draw_prob": 0.0,
                    "away_prob": 0.0,
                    "contributors": set(),
                }
            acc[key]["home_prob"] += w * r.home_prob
            if r.draw_prob is not None:
                acc[key]["draw_prob"] += w * r.draw_prob
            acc[key]["away_prob"] += w * r.away_prob
            acc[key]["sum_w"] += w

        ensemble_rows = []
        weights_json = json.dumps(weights)
        for v in acc.values():
            if v["sum_w"] > 0:
                ep = EnsemblePrediction(
                    run_id=run.id,
                    match_id=v["match_id"],
                    market=v["market"],
                    home_prob=v["home_prob"] / v["sum_w"],
                    draw_prob=v["draw_prob"] / v["sum_w"],
                    away_prob=v["away_prob"] / v["sum_w"],
                    model_weights=json.loads(weights_json),
                )
                ensemble_rows.append(ep)

        if ensemble_rows:
            db.add_all(ensemble_rows)

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.matches_count = target_limit
        await db.flush()

        return {
            "run_id": run.id,
            "status": run.status,
            "weighting": weighting,
            "weights": weights,
            "ensemble_rows": len(ensemble_rows),
        }
    except Exception as e:
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = str(e)
        await db.flush()
        return {"run_id": run.id, "status": run.status, "error": str(e)}
