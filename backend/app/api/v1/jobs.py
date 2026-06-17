from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.database import get_db
from app.models.job import ScheduledJob
from app.models.user import User
from app.schemas.job import ScheduledJobCreateRequest, ScheduledJobResponse

router = APIRouter()


@router.get("", response_model=list[ScheduledJobResponse])
async def list_scheduled_jobs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(ScheduledJob).order_by(ScheduledJob.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ScheduledJobResponse, status_code=201)
async def create_scheduled_job(
    body: ScheduledJobCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    job = ScheduledJob(
        name=body.name,
        task_type=body.task_type,
        cron_expression=body.cron_expression,
        config=body.config,
    )
    db.add(job)
    await db.flush()
    return job


@router.get("/{job_id}", response_model=ScheduledJobResponse)
async def get_scheduled_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await db.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    return job


@router.patch("/{job_id}/toggle", response_model=ScheduledJobResponse)
async def toggle_scheduled_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    job = await db.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    job.enabled = not job.enabled
    await db.flush()
    return job
