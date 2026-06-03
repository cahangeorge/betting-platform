"""Data expansion routes — fetch live stats, expand training data."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User
from app.services.stats.live_ingester import LiveStatsIngester

router = APIRouter(prefix="/data", tags=["data"])

# Global ingester reference (can be started/stopped)
_ingester: LiveStatsIngester | None = None


@router.post("/expand-csv", response_model=dict[str, Any])
async def expand_csv(
    seasons: str = "2024",
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch historical match data from football-data.org and append to CSV.

    seasons: comma-separated list, e.g. '2023,2024'
    Note: requires FOOTBALL_DATA_API_KEY env var to be set.
    """
    ingester = LiveStatsIngester()
    season_list = [int(s.strip()) for s in seasons.split(",") if s.strip().isdigit()]
    result = await ingester.expand_training_data(seasons=season_list or [2024])
    return {
        "status": "expanded",
        **result,
        "note": "Use /training/import-csv to import appended data into DB, then /training/fit to retrain",
    }


@router.get("/ingester/status", response_model=dict[str, Any])
async def ingester_status(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Check status of the live stats ingester."""
    global _ingester
    if not _ingester:
        return {"running": False}
    return {"running": _ingester._running, **{"stats": _ingester.stats}}


@router.post("/ingester/start", response_model=dict[str, Any])
async def start_ingester(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Start background live stats polling (60s interval)."""
    global _ingester
    if _ingester and _ingester._running:
        return {"status": "already_running"}
    _ingester = LiveStatsIngester(poll_interval=60)
    _ingester.start()
    return {"status": "started", "poll_interval_seconds": 60}


@router.post("/ingester/stop", response_model=dict[str, Any])
async def stop_ingester(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Stop background live stats polling."""
    global _ingester
    if not _ingester:
        return {"status": "not_running"}
    await _ingester.stop()
    _ingester = None
    return {"status": "stopped"}