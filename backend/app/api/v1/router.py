from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    auth,
    bankroll,
    catalog,
    dashboard,
    data,
    job_runs,
    jobs,
    live,
    matches,
    model_governance,
    predictions,
    provider,
    strategies,
    tickets,
    trading,
)

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
v1_router.include_router(matches.router, prefix="/matches", tags=["matches"])
v1_router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])
v1_router.include_router(provider.router, prefix="/provider", tags=["provider"])
v1_router.include_router(tickets.router, prefix="/tickets", tags=["tickets"])
v1_router.include_router(data.router, prefix="/data", tags=["data"])
v1_router.include_router(bankroll.router, prefix="/bankroll", tags=["bankroll"])
v1_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
v1_router.include_router(job_runs.router, prefix="/job-runs", tags=["job-runs"])
v1_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
v1_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
v1_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
v1_router.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
v1_router.include_router(live.router, prefix="/live", tags=["live"])
v1_router.include_router(trading.router, prefix="/trading", tags=["trading"])
v1_router.include_router(
    model_governance.router,
    prefix="/model-governance",
    tags=["model-governance"],
)
