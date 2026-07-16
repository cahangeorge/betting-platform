from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.job import ScheduledJobRun
from app.models.match import Match, MatchResultCorrection
from app.models.scrape import ScrapedDataset, ScrapeJob, ScrapeJobLog
from app.models.ticket import Settlement, Ticket, TicketLeg
from app.models.user import User
from app.schemas.data import (
    MatchResultCorrectionRequest,
    MatchResultCorrectionResponse,
    ResultRefreshRequest,
    ScrapedDatasetResponse,
    ScrapeJobCreateRequest,
    ScrapeJobLogPageResponse,
    ScrapeJobQueuedResponse,
    ScrapeJobResponse,
    WorldCupPipelineRequest,
)
from app.schemas.job import ScheduledJobRunPageResponse, ScheduledJobRunResponse
from app.services.run_authorization import can_read_run, can_read_scrape_job, stamp_owner
from app.services.scheduled_jobs import (
    TaskEnqueueError,
    enqueue_scrape_job_execution,
    enqueue_world_cup_pipeline_execution,
)
from app.services.scraper import create_result_refresh_job, create_scrape_job, execute_scrape_job

router = APIRouter()

TERMINAL_TICKET_STATUSES = {"won", "lost", "void", "settled"}


def _require_scrape_job_access(job: ScrapeJob, user: User) -> None:
    if not can_read_scrape_job(job, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Scrape job is not owned by the current user")


def _dataset_scrape_job_id(dataset: ScrapedDataset) -> int | None:
    data = dataset.data if isinstance(dataset.data, dict) else {}
    raw_job_id = data.get("job_id")
    return raw_job_id if isinstance(raw_job_id, int) and raw_job_id > 0 else None


async def _require_dataset_access(db: AsyncSession, dataset: ScrapedDataset, user: User) -> None:
    if getattr(user, "is_admin", False):
        return
    scrape_job_id = _dataset_scrape_job_id(dataset)
    scrape_job = await db.get(ScrapeJob, scrape_job_id) if scrape_job_id is not None else None
    if scrape_job is None or not can_read_scrape_job(scrape_job, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dataset is not owned by the current user")


@router.post("/scrape", response_model=ScrapeJobResponse, status_code=201)
async def start_scrape_job(
    body: ScrapeJobCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await create_scrape_job(db, body.job_type, body.league, stamp_owner(body.params, user.id))
    return job


@router.post("/scrape/{job_id}/execute", response_model=ScrapeJobResponse)
async def run_scrape_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing_job = await db.get(ScrapeJob, job_id)
    if not existing_job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    _require_scrape_job_access(existing_job, user)
    try:
        job = await execute_scrape_job(db, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return job


@router.post("/scrape/results-refresh", response_model=ScrapeJobQueuedResponse, status_code=202)
async def refresh_match_results(
    body: ResultRefreshRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Queue a targeted rescrape of known source URLs for explicit match IDs."""
    try:
        job = await create_result_refresh_job(db, body.match_ids, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    try:
        run = await enqueue_scrape_job_execution(db, scrape_job_id=job.id, triggered_by="api", user_id=user.id)
    except TaskEnqueueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "Task queue publish failed", "run_id": exc.run.id},
        ) from exc
    return _scrape_job_queued_response(job, run)


@router.post("/matches/{match_id}/result-corrections", response_model=MatchResultCorrectionResponse, status_code=201)
async def correct_match_result(
    match_id: int,
    body: MatchResultCorrectionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Apply an attributable final-score correction before any linked ticket is settled."""
    if not getattr(user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for match result corrections",
        )

    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    settled_ticket_stmt = (
        select(Ticket.id)
        .join(TicketLeg, TicketLeg.ticket_id == Ticket.id)
        .outerjoin(Settlement, Settlement.ticket_id == Ticket.id)
        .where(TicketLeg.match_id == match_id)
        .where(or_(Settlement.id.is_not(None), Ticket.status.in_(TERMINAL_TICKET_STATUSES)))
        .limit(1)
    )
    settled_ticket_result = await db.execute(settled_ticket_stmt)
    settled_ticket_id = settled_ticket_result.scalar_one_or_none()
    if settled_ticket_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot correct match result: linked ticket {settled_ticket_id} is already settled",
        )

    correction = MatchResultCorrection(
        match_id=match.id,
        corrected_by_user_id=user.id,
        source=body.source,
        reason=body.reason,
        previous_home_score=match.home_score,
        previous_away_score=match.away_score,
        previous_status=match.status,
        corrected_home_score=body.home_score,
        corrected_away_score=body.away_score,
        corrected_status="finished",
    )
    db.add(correction)
    match.home_score = body.home_score
    match.away_score = body.away_score
    match.status = "finished"
    await db.flush()
    return correction


def _scrape_job_queued_response(job: ScrapeJob, run: ScheduledJobRun) -> ScrapeJobQueuedResponse:
    payload = ScrapeJobQueuedResponse.model_validate(job)
    payload.queued_run_id = run.id
    payload.queued_run = ScheduledJobRunResponse.model_validate(run)
    return payload


@router.post("/scrape/{job_id}/execute-background", response_model=ScrapeJobQueuedResponse, status_code=202)
async def run_scrape_job_background(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    _require_scrape_job_access(job, user)
    try:
        run = await enqueue_scrape_job_execution(db, scrape_job_id=job.id, triggered_by="api", user_id=user.id)
    except TaskEnqueueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "Task queue publish failed", "run_id": exc.run.id},
        ) from exc
    return _scrape_job_queued_response(job, run)


@router.post("/world-cup-pipeline", response_model=ScrapeJobQueuedResponse, status_code=202)
async def start_world_cup_pipeline(
    body: WorldCupPipelineRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await create_scrape_job(
        db,
        "world_cup_pipeline",
        "world-cup",
        stamp_owner(body.model_dump(), user.id),
    )
    await db.commit()
    try:
        run = await enqueue_world_cup_pipeline_execution(db, scrape_job_id=job.id, user_id=user.id, triggered_by="api")
    except TaskEnqueueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "Task queue publish failed", "run_id": exc.run.id},
        ) from exc
    return _scrape_job_queued_response(job, run)


@router.get("/scrape", response_model=list[ScrapeJobResponse])
async def list_scrape_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(ScrapeJob).order_by(ScrapeJob.created_at.desc())
    result = await db.execute(stmt)
    jobs = list(result.scalars().all())
    if not getattr(user, "is_admin", False):
        jobs = [job for job in jobs if can_read_scrape_job(job, user)]
    offset = (page - 1) * per_page
    return jobs[offset : offset + per_page]


@router.get("/scrape/{job_id}", response_model=ScrapeJobResponse)
async def get_scrape_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    _require_scrape_job_access(job, user)
    return job


@router.get("/scrape/{job_id}/runs", response_model=ScheduledJobRunPageResponse)
async def get_scrape_job_runs(
    job_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    _require_scrape_job_access(job, user)

    stmt = (
        select(ScheduledJobRun)
        .where(ScheduledJobRun.scrape_job_id == job_id)
        .order_by(ScheduledJobRun.created_at.desc())
    )
    result = await db.execute(stmt)
    runs_for_job = list(result.scalars().all())
    if can_read_scrape_job(job, user):
        readable_runs = runs_for_job
    else:
        readable_runs = [run for run in runs_for_job if await can_read_run(db, run, user)]
        if not readable_runs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Scrape job is not owned by the current user"
            )

    total = len(readable_runs)
    offset = (page - 1) * per_page
    runs = readable_runs[offset : offset + per_page]
    return ScheduledJobRunPageResponse(runs=runs, total=total, page=page, per_page=per_page)


@router.get("/scrape/{job_id}/logs", response_model=ScrapeJobLogPageResponse)
async def get_scrape_job_logs(
    job_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    level: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    _require_scrape_job_access(job, user)

    count_stmt = select(func.count(ScrapeJobLog.id)).where(ScrapeJobLog.job_id == job_id)
    stmt = select(ScrapeJobLog).where(ScrapeJobLog.job_id == job_id)
    if level:
        count_stmt = count_stmt.where(ScrapeJobLog.level == level)
        stmt = stmt.where(ScrapeJobLog.level == level)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    stmt = (
        stmt.order_by(ScrapeJobLog.created_at.asc(), ScrapeJobLog.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    return ScrapeJobLogPageResponse(
        items=list(result.scalars().all()),
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/datasets", response_model=list[ScrapedDatasetResponse])
async def list_datasets(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(ScrapedDataset).order_by(ScrapedDataset.created_at.desc())
    result = await db.execute(stmt)
    datasets = list(result.scalars().all())
    if not getattr(user, "is_admin", False):
        job_ids = list(
            dict.fromkeys(
                job_id
                for dataset in datasets
                if (job_id := _dataset_scrape_job_id(dataset)) is not None
            )
        )
        jobs_result = await db.execute(select(ScrapeJob).where(ScrapeJob.id.in_(job_ids))) if job_ids else None
        jobs_by_id = {
            job.id: job
            for job in (jobs_result.scalars().all() if jobs_result is not None else [])
        }
        datasets = [
            dataset
            for dataset in datasets
            if (job_id := _dataset_scrape_job_id(dataset)) is not None
            and job_id in jobs_by_id
            and can_read_scrape_job(jobs_by_id[job_id], user)
        ]
    offset = (page - 1) * per_page
    return datasets[offset : offset + per_page]


@router.get("/datasets/{dataset_id}", response_model=ScrapedDatasetResponse)
async def get_dataset(
    dataset_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    dataset = await db.get(ScrapedDataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    await _require_dataset_access(db, dataset, user)
    return dataset
