from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.job import ScheduledJob, ScheduledJobRun
from app.models.user import User
from app.schemas.job import (
    ScheduledJobCreateRequest,
    ScheduledJobResponse,
    ScheduledJobRunPageResponse,
    ScheduledJobRunResponse,
)
from app.services.job_creation_idempotency import (
    create_idempotent_job,
    normalize_idempotency_key,
    request_fingerprint,
)
from app.services.run_authorization import can_read_scheduled_job, require_can_read_scheduled_job
from app.services.scheduled_jobs import (
    initialize_next_run,
    run_due_scheduled_jobs,
    stamp_created_by,
)

router = APIRouter()


@router.get("", response_model=list[ScheduledJobResponse])
async def list_scheduled_jobs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(ScheduledJob).order_by(ScheduledJob.created_at.desc())
    result = await db.execute(stmt)
    jobs = list(result.scalars().all())
    if user.is_admin:
        return jobs
    return [job for job in jobs if can_read_scheduled_job(job, user)]


@router.post("", response_model=ScheduledJobResponse, status_code=201)
async def create_scheduled_job(
    body: ScheduledJobCreateRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    async def create() -> ScheduledJob:
        job = ScheduledJob(
            name=body.name,
            task_type=body.task_type,
            cron_expression=body.cron_expression,
            config=stamp_created_by(body.config, user.id),
        )
        db.add(job)
        await db.flush()
        await initialize_next_run(db, job, now=datetime.now(timezone.utc))
        return job

    try:
        key = normalize_idempotency_key(idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if key is None:
        return await create()
    try:
        job, created = await create_idempotent_job(
            db,
            user_id=user.id,
            operation="scheduled_job_create",
            idempotency_key=key,
            fingerprint=request_fingerprint(body.model_dump(mode="json")),
            job_model=ScheduledJob,
            create=create,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return job


@router.post("/run-due", response_model=list[ScheduledJobRunResponse])
async def run_due_jobs(
    limit: int = Query(10, ge=1, le=50),
    job_id: int | None = Query(default=None, ge=1),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if job_id is None:
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="A job_id owned by the current user is required")
        return await run_due_scheduled_jobs(db, limit=limit)

    job = await db.get(ScheduledJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    require_can_read_scheduled_job(job, user)
    return await run_due_scheduled_jobs(db, limit=limit, job_ids=[job.id])


@router.get("/{job_id}/runs", response_model=ScheduledJobRunPageResponse)
async def list_scheduled_job_runs(
    job_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    job = await db.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    require_can_read_scheduled_job(job, _user)

    total_result = await db.execute(
        select(func.count()).select_from(ScheduledJobRun).where(ScheduledJobRun.scheduled_job_id == job_id)
    )
    total = int(total_result.scalar_one())
    stmt = (
        select(ScheduledJobRun)
        .where(ScheduledJobRun.scheduled_job_id == job_id)
        .order_by(ScheduledJobRun.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    return ScheduledJobRunPageResponse(runs=list(result.scalars().all()), total=total, page=page, per_page=per_page)


@router.get("/{job_id}", response_model=ScheduledJobResponse)
async def get_scheduled_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await db.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    require_can_read_scheduled_job(job, user)
    return job


@router.patch("/{job_id}/toggle", response_model=ScheduledJobResponse)
async def toggle_scheduled_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    job = await db.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    require_can_read_scheduled_job(job, _user)
    job.enabled = not job.enabled
    await db.flush()
    return job
