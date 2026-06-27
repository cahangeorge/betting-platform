from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import async_session_factory, get_db
from app.models.scrape import ScrapedDataset, ScrapeJob, ScrapeJobLog
from app.models.user import User
from app.schemas.data import (
    ScrapedDatasetResponse,
    ScrapeJobCreateRequest,
    ScrapeJobLogPageResponse,
    ScrapeJobResponse,
    WorldCupPipelineRequest,
)
from app.services.scraper import create_scrape_job, execute_scrape_job
from app.services.world_cup_pipeline import execute_world_cup_pipeline_job

router = APIRouter()


async def _execute_scrape_job_background(job_id: int) -> None:
    async with async_session_factory() as session:
        try:
            await execute_scrape_job(session, job_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@router.post("/scrape", response_model=ScrapeJobResponse, status_code=201)
async def start_scrape_job(
    body: ScrapeJobCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await create_scrape_job(db, body.job_type, body.league, body.params)
    return job


@router.post("/scrape/{job_id}/execute", response_model=ScrapeJobResponse)
async def run_scrape_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        job = await execute_scrape_job(db, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return job


@router.post("/scrape/{job_id}/execute-background", response_model=ScrapeJobResponse, status_code=202)
async def run_scrape_job_background(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    background_tasks.add_task(_execute_scrape_job_background, job.id)
    return job


@router.post("/world-cup-pipeline", response_model=ScrapeJobResponse, status_code=202)
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
        body.model_dump(),
    )
    await db.commit()
    background_tasks.add_task(execute_world_cup_pipeline_job, job.id, user.id)
    return job


@router.get("/scrape", response_model=list[ScrapeJobResponse])
async def list_scrape_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/scrape/{job_id}", response_model=ScrapeJobResponse)
async def get_scrape_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    return job


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
    stmt = (
        select(ScrapedDataset).order_by(ScrapedDataset.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/datasets/{dataset_id}", response_model=ScrapedDatasetResponse)
async def get_dataset(
    dataset_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    dataset = await db.get(ScrapedDataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset
