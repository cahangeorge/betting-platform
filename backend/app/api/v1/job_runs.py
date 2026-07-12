from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.job import ScheduledJobRun
from app.models.user import User
from app.schemas.job import ScheduledJobRunResponse
from app.services.run_authorization import require_can_read_run

router = APIRouter()


@router.get("/{run_id}", response_model=ScheduledJobRunResponse)
async def get_job_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = await db.get(ScheduledJobRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Scheduled job run not found")
    await require_can_read_run(db, run, user)
    return run
