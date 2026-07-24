from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.prediction import ModelPrediction, PredictionRun
from app.models.strategy import Strategy
from app.models.ticket import Settlement, Ticket, TicketBatch, TicketLeg
from app.models.user import User
from app.schemas.ticket import (
    BetPlacementResponse,
    SettlementResponse,
    TicketBatchActivateRequest,
    TicketBatchActivateResponse,
    TicketBatchDiscardResponse,
    TicketBatchLineageResponse,
    TicketBatchRefreshRequest,
    TicketBatchRefreshResponse,
    TicketBatchResponse,
    TicketCreateRequest,
    TicketDetailResponse,
    TicketGenerateRequest,
    TicketGenerateResponse,
    TicketLineageLegResponse,
    TicketLineageTicketResponse,
    TicketPageResponse,
    TicketPreflightRequest,
    TicketPreflightResponse,
    TicketResponse,
    TicketSettlementRunResponse,
    TicketStatsResponse,
    TicketSwapLegsRequest,
    TicketSwapLegsResponse,
)
from app.services.result_settlement import settle_due_tickets
from app.services.ticket_engine import (
    TicketActivationConflictError,
    TicketBatchDiscardConflictError,
    TicketGenerationError,
    TicketManualRiskConflictError,
    TicketRefreshConflictError,
    TicketRiskPolicyRequiredError,
    TicketSettlementConflictError,
    activate_ticket_batch,
    create_manual_ticket,
    discard_generated_ticket_batch,
    generate_tickets,
    place_bet,
    preflight_ticket_generation,
    refresh_ticket_batch,
    settle_ticket,
    swap_ticket_legs,
)

router = APIRouter()


def _ticket_generation_error_detail(exc: TicketGenerationError) -> str:
    excluded = int(exc.report.get("excluded_predictions", 0) or 0)
    scanned = int(exc.report.get("scanned_predictions", 0) or 0)
    reasons = exc.report.get("excluded_by_reason")
    reason_detail = ""
    if isinstance(reasons, dict) and reasons:
        reason_detail = ": " + ", ".join(f"{reason}={count}" for reason, count in sorted(reasons.items()))
    requested_detail = ""
    if "requested_predictions" in exc.report:
        requested = int(exc.report.get("requested_predictions", 0) or 0)
        missing = int(exc.report.get("missing_predictions", 0) or 0)
        missing_ids = exc.report.get("missing_prediction_ids") or []
        requested_detail = f" Requested {requested}; missing {missing}"
        if missing_ids:
            requested_detail += f" (IDs: {', '.join(str(value) for value in missing_ids)})"
        requested_detail += "."
    return f"{exc}.{requested_detail} Excluded {excluded}/{scanned} predictions{reason_detail}."


def _resolve_ticket_reference(ticket: Ticket) -> str:
    placements = getattr(ticket, "placements", []) or []
    for placement in placements:
        reference = getattr(placement, "reference", None)
        if reference:
            return reference
    return f"TKT-{ticket.id}"


def _serialize_ticket_summary(
    ticket: Ticket,
    *,
    reference: str,
    actual_return: float | None,
    settled_at,
) -> TicketResponse:
    def serialize_leg_match(leg: TicketLeg) -> dict | None:
        match = getattr(leg, "match", None)
        if match is None:
            return None
        return {
            "id": match.id,
            "league": getattr(match, "competition", None) or getattr(match, "league", None),
            "home_team": match.home_team,
            "away_team": match.away_team,
            "start_time": getattr(match, "match_date", None) or getattr(match, "start_time", None),
            "status": match.status,
        }

    legs = [
        {
            "id": leg.id,
            "ticket_id": leg.ticket_id,
            "model_prediction_id": leg.model_prediction_id,
            "match_id": leg.match_id,
            "selection": leg.selection,
            "market": leg.market,
            "odds": leg.odds,
            "bookmaker": leg.bookmaker,
            "prediction_run_id_snapshot": getattr(leg, "prediction_run_id_snapshot", None),
            "model_probability_snapshot": getattr(leg, "model_probability_snapshot", None),
            "market_probability_snapshot": getattr(leg, "market_probability_snapshot", None),
            "market_probability_basis_snapshot": getattr(leg, "market_probability_basis_snapshot", None),
            "expected_value_snapshot": getattr(leg, "expected_value_snapshot", None),
            "edge_pct_snapshot": getattr(leg, "edge_pct_snapshot", None),
            "reliability_label_snapshot": getattr(leg, "reliability_label_snapshot", None),
            "reliability_score_snapshot": getattr(leg, "reliability_score_snapshot", None),
            "status": leg.status,
            "created_at": leg.created_at,
            "match": serialize_leg_match(leg),
        }
        for leg in getattr(ticket, "legs", []) or []
    ]

    return TicketResponse(
        id=ticket.id,
        reference=reference,
        user_id=ticket.user_id,
        bankroll_id=ticket.bankroll_id,
        batch_id=ticket.batch_id,
        ticket_type=ticket.ticket_type,
        stake=ticket.stake,
        total_odds=ticket.total_odds,
        potential_return=ticket.potential_return,
        actual_return=actual_return,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        settled_at=settled_at,
        legs=legs,
    )


def _serialize_lineage_run(run: PredictionRun, strategy_name: str | None = None) -> dict:
    """Return a stable, read-only run snapshot for ticket lineage."""

    payload = {
        "id": run.id,
        "user_id": run.user_id,
        "name": run.name,
        "model_type": run.model_type,
        "ensemble": run.ensemble,
        "status": run.status,
        "matches_count": run.matches_count,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "error": run.error,
        "source_dataset_id": run.source_dataset_id,
        "strategy_id": run.strategy_id,
        "input_hash": run.input_hash,
        "input_context": run.input_context,
        "created_at": run.created_at,
    }
    # ``strategy_name`` is intentionally optional so old rows and SQLite
    # databases that have no strategy metadata remain valid.
    if strategy_name is not None:
        payload["strategy_name"] = strategy_name
    return payload


def _serialize_ticket_lineage(ticket: Ticket) -> TicketLineageTicketResponse:
    legs: list[TicketLineageLegResponse] = []
    for leg in getattr(ticket, "legs", []) or []:
        prediction = getattr(leg, "model_prediction", None)
        run = getattr(prediction, "run", None) if prediction is not None else None
        legs.append(
            TicketLineageLegResponse(
                id=leg.id,
                ticket_id=leg.ticket_id,
                model_prediction_id=leg.model_prediction_id,
                match_id=leg.match_id,
                selection=leg.selection,
                market=leg.market,
                odds=leg.odds,
                bookmaker=leg.bookmaker,
                prediction_run_id_snapshot=getattr(leg, "prediction_run_id_snapshot", None),
                model_probability_snapshot=getattr(leg, "model_probability_snapshot", None),
                market_probability_snapshot=getattr(leg, "market_probability_snapshot", None),
                market_probability_basis_snapshot=getattr(leg, "market_probability_basis_snapshot", None),
                expected_value_snapshot=getattr(leg, "expected_value_snapshot", None),
                edge_pct_snapshot=getattr(leg, "edge_pct_snapshot", None),
                reliability_label_snapshot=getattr(leg, "reliability_label_snapshot", None),
                reliability_score_snapshot=getattr(leg, "reliability_score_snapshot", None),
                status=leg.status,
                created_at=leg.created_at,
                match=_serialize_lineage_match(leg),
                prediction=prediction,
                run=run,
            )
        )
    return TicketLineageTicketResponse(
        id=ticket.id,
        reference=_resolve_ticket_reference(ticket),
        user_id=ticket.user_id,
        bankroll_id=ticket.bankroll_id,
        batch_id=ticket.batch_id,
        ticket_type=ticket.ticket_type,
        stake=ticket.stake,
        total_odds=ticket.total_odds,
        potential_return=ticket.potential_return,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        legs=legs,
    )


def _serialize_lineage_match(leg: TicketLeg) -> dict | None:
    match = getattr(leg, "match", None)
    if match is None:
        return None
    return {
        "id": match.id,
        "league": getattr(match, "competition", None) or getattr(match, "league", None),
        "home_team": match.home_team,
        "away_team": match.away_team,
        "start_time": getattr(match, "match_date", None) or getattr(match, "start_time", None),
        "status": match.status,
    }


def _compute_ticket_stats(
    tickets: list[Ticket], settlements_by_ticket_id: dict[int, Settlement]
) -> dict[str, float | int]:
    return {
        "total": len(tickets),
        "won": sum(1 for ticket in tickets if ticket.status == "won"),
        "lost": sum(1 for ticket in tickets if ticket.status == "lost"),
        "profit_loss": round(
            sum(
                (settlements_by_ticket_id.get(ticket.id).pnl if settlements_by_ticket_id.get(ticket.id) else 0.0)
                for ticket in tickets
            ),
            2,
        ),
    }


async def _load_latest_settlements(db: AsyncSession, ticket_ids: list[int]) -> dict[int, Settlement]:
    if not ticket_ids:
        return {}

    result = await db.execute(select(Settlement).where(Settlement.ticket_id.in_(ticket_ids)))
    settlements = result.scalars().all()

    latest_by_ticket_id: dict[int, Settlement] = {}
    for settlement in settlements:
        if settlement.ticket_id is None:
            continue
        previous = latest_by_ticket_id.get(settlement.ticket_id)
        if previous is None or settlement.settled_at > previous.settled_at:
            latest_by_ticket_id[settlement.ticket_id] = settlement

    return latest_by_ticket_id


async def _load_ticket_summary(db: AsyncSession, ticket_id: int, user_id: int) -> TicketResponse | None:
    summaries = await _load_ticket_summaries(db, [ticket_id], user_id)
    return summaries[0] if summaries else None


async def _load_ticket_summaries(
    db: AsyncSession,
    ticket_ids: list[int],
    user_id: int,
) -> list[TicketResponse]:
    ordered_ids = list(dict.fromkeys(ticket_ids))
    if not ordered_ids:
        return []
    stmt = (
        select(Ticket)
        .options(
            selectinload(Ticket.legs).selectinload(TicketLeg.match),
            selectinload(Ticket.placements),
        )
        .where(Ticket.id.in_(ordered_ids), Ticket.user_id == user_id)
    )
    result = await db.execute(stmt)
    tickets_by_id = {ticket.id: ticket for ticket in result.scalars().unique().all()}

    settlements_by_ticket_id = await _load_latest_settlements(db, list(tickets_by_id))
    summaries: list[TicketResponse] = []
    for ticket_id in ordered_ids:
        ticket = tickets_by_id.get(ticket_id)
        if ticket is None:
            continue
        settlement = settlements_by_ticket_id.get(ticket.id)
        summaries.append(
            _serialize_ticket_summary(
                ticket,
                reference=_resolve_ticket_reference(ticket),
                actual_return=settlement.return_amount if settlement else None,
                settled_at=settlement.settled_at if settlement else None,
            )
        )
    return summaries


@router.get("", response_model=list[TicketResponse])
async def list_tickets(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = None,
    batch_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(Ticket)
        .options(
            selectinload(Ticket.legs).selectinload(TicketLeg.match),
            selectinload(Ticket.placements),
        )
        .where(Ticket.user_id == user.id)
    )
    if status:
        stmt = stmt.where(Ticket.status == status)
    if batch_id:
        stmt = stmt.where(Ticket.batch_id == batch_id)
    stmt = stmt.order_by(Ticket.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(stmt)
    tickets = result.scalars().unique().all()
    settlements_by_ticket_id = await _load_latest_settlements(db, [ticket.id for ticket in tickets])

    return [
        _serialize_ticket_summary(
            ticket,
            reference=_resolve_ticket_reference(ticket),
            actual_return=settlements_by_ticket_id[ticket.id].return_amount
            if ticket.id in settlements_by_ticket_id
            else None,
            settled_at=settlements_by_ticket_id[ticket.id].settled_at
            if ticket.id in settlements_by_ticket_id
            else None,
        )
        for ticket in tickets
    ]


@router.get("/page", response_model=TicketPageResponse)
async def list_tickets_page(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = None,
    batch_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    count_stmt = select(func.count(Ticket.id)).where(Ticket.user_id == user.id)
    stmt = (
        select(Ticket)
        .options(
            selectinload(Ticket.legs).selectinload(TicketLeg.match),
            selectinload(Ticket.placements),
        )
        .where(Ticket.user_id == user.id)
    )
    if status:
        count_stmt = count_stmt.where(Ticket.status == status)
        stmt = stmt.where(Ticket.status == status)
    if batch_id:
        count_stmt = count_stmt.where(Ticket.batch_id == batch_id)
        stmt = stmt.where(Ticket.batch_id == batch_id)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    stmt = stmt.order_by(Ticket.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(stmt)
    tickets = result.scalars().unique().all()
    settlements_by_ticket_id = await _load_latest_settlements(db, [ticket.id for ticket in tickets])

    return TicketPageResponse(
        items=[
            _serialize_ticket_summary(
                ticket,
                reference=_resolve_ticket_reference(ticket),
                actual_return=settlements_by_ticket_id[ticket.id].return_amount
                if ticket.id in settlements_by_ticket_id
                else None,
                settled_at=settlements_by_ticket_id[ticket.id].settled_at
                if ticket.id in settlements_by_ticket_id
                else None,
            )
            for ticket in tickets
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/stats", response_model=TicketStatsResponse)
async def get_ticket_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ranked_settlements = (
        select(
            Settlement.ticket_id.label("ticket_id"),
            Settlement.pnl.label("pnl"),
            func.row_number()
            .over(
                partition_by=Settlement.ticket_id,
                order_by=(Settlement.settled_at.desc(), Settlement.id.desc()),
            )
            .label("settlement_rank"),
        )
        .where(Settlement.ticket_id.is_not(None))
        .subquery()
    )
    stats_stmt = (
        select(
            func.count(Ticket.id).label("total"),
            func.coalesce(func.sum(case((Ticket.status == "won", 1), else_=0)), 0).label("won"),
            func.coalesce(func.sum(case((Ticket.status == "lost", 1), else_=0)), 0).label("lost"),
            func.coalesce(func.sum(ranked_settlements.c.pnl), 0.0).label("profit_loss"),
        )
        .outerjoin(
            ranked_settlements,
            and_(
                ranked_settlements.c.ticket_id == Ticket.id,
                ranked_settlements.c.settlement_rank == 1,
            ),
        )
        .where(Ticket.user_id == user.id)
    )
    row = (await db.execute(stats_stmt)).one()
    return TicketStatsResponse(
        total=int(row.total or 0),
        won=int(row.won or 0),
        lost=int(row.lost or 0),
        profit_loss=round(float(row.profit_loss or 0.0), 2),
    )


@router.post("/settle-due", response_model=TicketSettlementRunResponse)
async def settle_due_tickets_endpoint(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await settle_due_tickets(db, user_id=user.id)


@router.get("/batches", response_model=list[TicketBatchResponse])
async def list_batches(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(TicketBatch)
        .join(Ticket, Ticket.batch_id == TicketBatch.id)
        .where(Ticket.user_id == user.id)
        .order_by(TicketBatch.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    return result.scalars().unique().all()


@router.get("/batches/{batch_id}/tickets", response_model=list[TicketResponse])
async def list_batch_tickets(
    batch_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.legs).selectinload(TicketLeg.match),
            selectinload(Ticket.placements),
        )
        .where(Ticket.user_id == user.id, Ticket.batch_id == batch_id)
        .order_by(Ticket.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    tickets = result.scalars().unique().all()
    settlements_by_ticket_id = await _load_latest_settlements(db, [ticket.id for ticket in tickets])

    return [
        _serialize_ticket_summary(
            ticket,
            reference=_resolve_ticket_reference(ticket),
            actual_return=settlements_by_ticket_id[ticket.id].return_amount
            if ticket.id in settlements_by_ticket_id
            else None,
            settled_at=settlements_by_ticket_id[ticket.id].settled_at
            if ticket.id in settlements_by_ticket_id
            else None,
        )
        for ticket in tickets
    ]


@router.get("/batches/{batch_id}/lineage", response_model=TicketBatchLineageResponse)
async def get_ticket_batch_lineage(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the read-only prediction lineage behind a generated batch.

    Ownership is checked through the batch's tickets rather than the optional
    bankroll field. This keeps draft batches private and works for historical
    rows created before explicit bankroll ownership was persisted.
    """

    stmt = (
        select(TicketBatch)
        .join(Ticket, Ticket.batch_id == TicketBatch.id)
        .options(
            selectinload(TicketBatch.tickets).selectinload(Ticket.legs).selectinload(TicketLeg.match),
            selectinload(TicketBatch.tickets)
            .selectinload(Ticket.legs)
            .selectinload(TicketLeg.model_prediction)
            .selectinload(ModelPrediction.run),
            selectinload(TicketBatch.tickets).selectinload(Ticket.placements),
        )
        .where(TicketBatch.id == batch_id, Ticket.user_id == user.id)
    )
    result = await db.execute(stmt)
    batch = result.unique().scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="Ticket batch not found")

    tickets = [ticket for ticket in (batch.tickets or []) if ticket.user_id == user.id]
    source_run_ids = list(getattr(batch, "source_prediction_run_ids", []) or [])
    runs: list[PredictionRun] = []
    if source_run_ids:
        runs_result = await db.execute(
            select(PredictionRun).where(
                PredictionRun.id.in_(source_run_ids),
                PredictionRun.user_id == user.id,
            )
        )
        runs_by_id = {run.id: run for run in runs_result.scalars().all()}
        runs = [runs_by_id[run_id] for run_id in source_run_ids if run_id in runs_by_id]

    strategy_ids = list({run.strategy_id for run in runs if run.strategy_id is not None})
    strategies_by_id: dict[int, Strategy] = {}
    if strategy_ids:
        strategies_result = await db.execute(select(Strategy).where(Strategy.id.in_(strategy_ids)))
        strategies_by_id = {strategy.id: strategy for strategy in strategies_result.scalars().all()}

    source_run_payloads = [
        _serialize_lineage_run(
            run,
            strategy_name=getattr(strategies_by_id.get(run.strategy_id), "name", None),
        )
        for run in runs
    ]

    return TicketBatchLineageResponse(
        id=batch.id,
        bankroll_id=batch.bankroll_id,
        source_prediction_run_id=batch.source_prediction_run_id,
        source_prediction_run_ids=source_run_ids,
        name=batch.name,
        strategy=batch.strategy,
        tickets_count=batch.tickets_count,
        total_stake=batch.total_stake,
        generation_report=batch.generation_report,
        created_at=batch.created_at,
        source_runs=source_run_payloads,
        tickets=[_serialize_ticket_lineage(ticket) for ticket in tickets],
    )


@router.post("/generate", response_model=TicketGenerateResponse, status_code=201)
async def generate_ticket_batch(
    body: TicketGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        batch, tickets = await generate_tickets(
            db=db,
            user_id=user.id,
            bankroll_id=body.bankroll_id,
            run_id=body.run_id,
            run_ids=body.run_ids,
            prediction_ids=body.prediction_ids,
            ticket_count=body.ticket_count,
            difficulty=body.difficulty,
            ticket_format=body.ticket_format,
            accumulator_risk_acknowledged=body.accumulator_risk_acknowledged,
            market_types=body.market_types,
            min_odds=body.min_odds,
            max_odds=body.max_odds,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TicketRiskPolicyRequiredError as exc:
        raise HTTPException(
            status_code=428,
            detail={"code": "risk_policy_required", "message": str(exc), "report": exc.report},
        ) from exc
    except TicketGenerationError as exc:
        raise HTTPException(status_code=400, detail=_ticket_generation_error_detail(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summaries = await _load_ticket_summaries(db, [ticket.id for ticket in tickets], user.id)
    return TicketGenerateResponse(
        batch_id=batch.id,
        revision=getattr(batch, "revision", 1),
        source_prediction_run_id=getattr(batch, "source_prediction_run_id", None),
        source_prediction_run_ids=getattr(batch, "source_prediction_run_ids", []),
        risk_policy_version=getattr(batch, "risk_policy_version", None),
        risk_assessment=getattr(batch, "risk_assessment", None),
        staking_snapshot=getattr(batch, "staking_snapshot", None),
        generation_report=getattr(batch, "generation_report", None) or {},
        tickets=summaries,
    )


@router.post("/preflight", response_model=TicketPreflightResponse)
async def preflight_ticket_batch(
    body: TicketPreflightRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Check all risk tiers without creating a draft batch or ticket rows."""

    try:
        report = await preflight_ticket_generation(
            db=db,
            user_id=user.id,
            bankroll_id=body.bankroll_id,
            run_id=body.run_id,
            run_ids=body.run_ids,
            prediction_ids=body.prediction_ids,
            market_types=body.market_types,
            min_odds=body.min_odds,
            max_odds=body.max_odds,
            ticket_format=body.ticket_format,
            accumulator_risk_acknowledged=body.accumulator_risk_acknowledged,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    risk_assessment = report.get("risk_assessment")
    blockers = risk_assessment.get("blockers", []) if isinstance(risk_assessment, dict) else []
    if any(blocker.get("code") == "risk_policy_required" for blocker in blockers if isinstance(blocker, dict)):
        raise HTTPException(
            status_code=428,
            detail={"code": "risk_policy_required", "message": "An explicit risk policy is required"},
        )
    return TicketPreflightResponse.model_validate(report)


@router.post("/batches/{batch_id}/activate", response_model=TicketBatchActivateResponse)
async def activate_generated_ticket_batch(
    batch_id: int,
    body: TicketBatchActivateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        batch, tickets, debited_amount = await activate_ticket_batch(
            db=db,
            user_id=user.id,
            batch_id=batch_id,
            expected_revision=body.expected_revision,
            review_acknowledged=body.review_acknowledged,
            accepted_warning_codes=body.accepted_warning_codes,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TicketActivationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summaries = await _load_ticket_summaries(db, [ticket.id for ticket in tickets], user.id)
    return TicketBatchActivateResponse(
        batch_id=batch.id,
        status="activated",
        debited_amount=debited_amount,
        tickets=summaries,
    )


@router.post("/batches/{batch_id}/refresh", response_model=TicketBatchRefreshResponse)
async def refresh_generated_ticket_batch(
    batch_id: int,
    body: TicketBatchRefreshRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        batch, tickets = await refresh_ticket_batch(
            db,
            user_id=user.id,
            batch_id=batch_id,
            expected_revision=body.expected_revision,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TicketRefreshConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summaries = await _load_ticket_summaries(db, [ticket.id for ticket in tickets], user.id)
    return TicketBatchRefreshResponse(
        batch_id=batch.id,
        revision=batch.revision,
        generation_report=batch.generation_report or {},
        risk_assessment=batch.risk_assessment,
        staking_snapshot=batch.staking_snapshot,
        tickets=summaries,
    )


@router.delete("/batches/{batch_id}", response_model=TicketBatchDiscardResponse)
async def discard_generated_batch(
    batch_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        discarded_batch_id, discarded_tickets = await discard_generated_ticket_batch(
            db=db,
            user_id=user.id,
            batch_id=batch_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TicketBatchDiscardConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return TicketBatchDiscardResponse(
        batch_id=discarded_batch_id,
        discarded_tickets=discarded_tickets,
    )


@router.post("/batches/{batch_id}/swap-legs", response_model=TicketSwapLegsResponse)
async def swap_generated_ticket_legs(
    batch_id: int,
    body: TicketSwapLegsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        source_ticket, target_ticket = await swap_ticket_legs(
            db=db,
            user_id=user.id,
            batch_id=batch_id,
            source_ticket_id=body.source_ticket_id,
            source_leg_id=body.source_leg_id,
            target_ticket_id=body.target_ticket_id,
            target_leg_id=body.target_leg_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summaries = await _load_ticket_summaries(db, [source_ticket.id, target_ticket.id], user.id)
    if len(summaries) != 2:
        raise HTTPException(status_code=500, detail="Updated tickets could not be reloaded")
    return TicketSwapLegsResponse(source_ticket=summaries[0], target_ticket=summaries[1])


@router.post("", response_model=TicketResponse, status_code=201)
async def create_new_ticket(
    body: TicketCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        ticket = await create_manual_ticket(
            db=db,
            user_id=user.id,
            ticket_type=body.ticket_type,
            stake=body.stake,
            bankroll_id=body.bankroll_id,
            legs_data=[leg.model_dump(exclude_none=True) for leg in body.legs],
            accumulator_risk_acknowledged=body.accumulator_risk_acknowledged,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TicketRiskPolicyRequiredError as exc:
        raise HTTPException(
            status_code=428,
            detail={"code": "risk_policy_required", "message": str(exc), "report": exc.report},
        ) from exc
    except TicketManualRiskConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "risk_policy_blocked", "message": str(exc), "report": exc.report},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summary = await _load_ticket_summary(db, ticket.id, user.id)
    if summary is None:
        raise HTTPException(status_code=500, detail="Created ticket could not be reloaded")
    return summary


@router.get("/{ticket_id}", response_model=TicketDetailResponse)
async def get_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(Ticket)
        .options(selectinload(Ticket.legs), selectinload(Ticket.placements))
        .where(Ticket.id == ticket_id, Ticket.user_id == user.id)
    )
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post(
    "/{ticket_id}/place",
    response_model=BetPlacementResponse,
    summary="Record a manual bookmaker placement",
    description=(
        "Manual bookkeeping only. This endpoint does not execute a paper or live order. "
        "Use POST /api/v1/trading/executions for the isolated paper execution workflow."
    ),
)
async def place_ticket(
    ticket_id: int,
    bookmaker: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user.id)
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status != "open":
        raise HTTPException(status_code=409, detail="Only active open tickets can be placed")
    placement = await place_bet(db, ticket_id, bookmaker)
    return placement


@router.post("/{ticket_id}/settle", response_model=SettlementResponse)
async def settle_ticket_endpoint(
    ticket_id: int,
    outcome: Literal["won", "lost", "void"],
    return_amount: float = Query(default=0.0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user.id)
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status != "open":
        raise HTTPException(status_code=409, detail="Only active open tickets can be settled")
    try:
        result_data = await settle_ticket(
            db,
            ticket_id,
            outcome,
            return_amount,
            user_id=user.id,
        )
    except TicketSettlementConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SettlementResponse.model_validate(result_data)
