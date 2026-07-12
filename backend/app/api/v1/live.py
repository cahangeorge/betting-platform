import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.match import Match, MatchSource, MatchStat, OddsEntry
from app.models.scrape import ScrapeJob
from app.models.prediction import ModelPrediction, PredictionRun
from app.models.user import User
from app.schemas.match import (
    LiveHeartbeatResponse,
    LiveMatchResponse,
    LiveOverviewResponse,
    LiveValueCandidateResponse,
)

router = APIRouter(tags=["live"])

LIVE_STALE_SECONDS = 90
LIVE_BETSLIP_MAX_DATA_AGE_SECONDS = 30
LIVE_MODEL_DRIFT_MAX_SECONDS = 300
LIVE_MODEL_ODDS_SKEW_SECONDS = 45
LIVE_VALUE_MAX_CANDIDATES = 3
LIVE_ACTIVE_STATUSES = {"live", "running", "active", "in_play", "halftime", "ht"}
LIVE_FINISHED_STATUSES = {"finished", "ft", "fulltime"}
LIVE_1X2_MARKET_ALIASES = {"1x2", "matchwinner", "match_winner", "home_away", "homeaway"}


def _safe_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_max_datetime(values: list[datetime | None]) -> datetime | None:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return max(cleaned)


def _normalize_match_status(value: str | None) -> str:
    return (value or "").strip().lower()


def _age_seconds(timestamp: datetime | None, now: datetime) -> int | None:
    if timestamp is None:
        return None
    return max(0, int((now - timestamp).total_seconds()))


def _resolve_match_minute(match: Match, now: datetime) -> int | None:
    status = _normalize_match_status(match.status)
    if status in LIVE_FINISHED_STATUSES:
        return 90
    if status in {"halftime", "ht", "half_time"}:
        return 45

    if not match.match_date:
        return None

    if status in LIVE_ACTIVE_STATUSES:
        elapsed = int((now - match.match_date).total_seconds() // 60)
        if elapsed < 0:
            return 0
        return min(elapsed, 120)
    return None


def _latest_record(records: list[Any]) -> Any | None:
    if not records:
        return None
    return max(records, key=lambda record: record.created_at or datetime.fromtimestamp(0, tz=timezone.utc))


def _build_momentum(stat: MatchStat | None) -> tuple[str, str]:
    if not stat:
        return "neutral", "weak"

    home_pressure = (stat.home_xg or 0.0) * 2.0 + (stat.shots_home or 0) * 0.25
    away_pressure = (stat.away_xg or 0.0) * 2.0 + (stat.shots_away or 0) * 0.25
    total = home_pressure + away_pressure

    if total <= 0:
        return "neutral", "weak"

    diff = home_pressure - away_pressure
    ratio = diff / total

    if abs(ratio) >= 0.35:
        return ("home" if ratio > 0 else "away", "overwhelming")
    if abs(ratio) >= 0.2:
        return ("home" if ratio > 0 else "away", "strong")
    if abs(ratio) >= 0.1:
        return ("home" if ratio > 0 else "away", "moderate")
    return "neutral", "weak"


def _select_bookmaker_odds(odds: list[OddsEntry]) -> list[OddsEntry]:
    if not odds:
        return []

    primary_market = [entry for entry in odds if _normalize_live_market(entry.market) in LIVE_1X2_MARKET_ALIASES]
    selected = primary_market or odds
    return sorted(selected, key=lambda entry: entry.created_at or datetime.fromtimestamp(0, tz=timezone.utc), reverse=True)


def _normalize_live_market(value: str) -> str:
    return re.sub(r"[^a-z0-9_:.]+", "", value.strip().lower())


def _resolve_live_bookmaker_odds(
    odds_entries: list[OddsEntry], outcome: str
) -> tuple[float | None, str, datetime | None]:
    candidates = [
        entry for entry in odds_entries if _normalize_live_market(entry.market) in LIVE_1X2_MARKET_ALIASES
    ]
    if not candidates:
        return None, "", None

    outcome_field = {
        "home": "home_odds",
        "draw": "draw_odds",
        "away": "away_odds",
    }.get(outcome, "home_odds")

    best_entry = None
    for entry in candidates:
        value = getattr(entry, outcome_field, None)
        if value is None or value <= 1:
            continue
        if best_entry is None or value > getattr(best_entry, outcome_field):
            best_entry = entry

    if best_entry is None:
        return None, outcome_field, None

    return getattr(best_entry, outcome_field), best_entry.bookmaker, best_entry.timestamp or best_entry.created_at


def _normalize_live_confidence_band(
    edge_pct: float, prediction_age_seconds: int | None
) -> str:
    if prediction_age_seconds is not None:
        if edge_pct >= 5.0 and prediction_age_seconds <= 180:
            return "high"
        if edge_pct >= 2.5 and prediction_age_seconds <= 900:
            return "medium"
        return "low"

    if edge_pct >= 6.0:
        return "high"
    if edge_pct >= 3.0:
        return "medium"
    return "low"


def _build_live_value_candidates(
    match: Match, predictions: list[ModelPrediction], now: datetime, min_edge: float, bridge_ready: bool
) -> list[LiveValueCandidateResponse]:
    candidates: list[LiveValueCandidateResponse] = []
    match_status = _normalize_match_status(match.status)
    is_live_match = match_status in LIVE_ACTIVE_STATUSES

    for prediction in predictions:
        market = _normalize_live_market(prediction.market)
        if market not in {"1x2", "matchwinner", "match_winner", "home_away", "homeaway"}:
            continue

        outcomes = [
            ("home", prediction.home_prob),
            ("draw", prediction.draw_prob),
            ("away", prediction.away_prob),
        ]

        for selection, model_prob in outcomes:
            if model_prob is None or model_prob <= 0:
                continue

            odds, bookmaker, odds_timestamp = _resolve_live_bookmaker_odds(list(match.odds), selection)
            if odds is None:
                continue

            implied = 1 / odds
            edge_pct = (model_prob - implied) * 100
            if edge_pct < min_edge:
                continue

            selection_age_seconds = _age_seconds(prediction.created_at, now)
            odds_freshness_seconds = _age_seconds(odds_timestamp, now)
            ages = [age for age in (selection_age_seconds, odds_freshness_seconds) if age is not None]
            data_age_seconds = max(ages) if ages else None
            source_ok = bridge_ready and is_live_match and bool(bookmaker) and odds_timestamp is not None
            model_drift_flag = (
                selection_age_seconds is None
                or selection_age_seconds > LIVE_MODEL_DRIFT_MAX_SECONDS
                or (
                    selection_age_seconds is not None
                    and odds_freshness_seconds is not None
                    and selection_age_seconds > odds_freshness_seconds + LIVE_MODEL_ODDS_SKEW_SECONDS
                )
            )

            block_reasons: list[str] = []
            if not bridge_ready:
                block_reasons.append("bridge_not_ready")
            if not is_live_match:
                block_reasons.append("match_not_live")
            if odds_timestamp is None:
                block_reasons.append("odds_missing_timestamp")
            if selection_age_seconds is None:
                block_reasons.append("prediction_missing_timestamp")
            if data_age_seconds is None:
                block_reasons.append("data_age_unknown")
            elif data_age_seconds >= LIVE_BETSLIP_MAX_DATA_AGE_SECONDS:
                block_reasons.append("data_stale")
            if model_drift_flag:
                block_reasons.append("model_drift")

            is_betslip_eligible = (
                source_ok
                and data_age_seconds is not None
                and data_age_seconds < LIVE_BETSLIP_MAX_DATA_AGE_SECONDS
                and not model_drift_flag
            )

            score_gap = None
            if match.home_score is not None and match.away_score is not None:
                score_gap = float(match.home_score - match.away_score)

            candidates.append(
                LiveValueCandidateResponse(
                    market="1x2",
                    selection=selection,
                    odds=odds,
                    model_probability=model_prob,
                    implied_probability=implied,
                    edge=edge_pct,
                    expected_value=(model_prob * odds) - 1,
                    spread=score_gap,
                    source=f"odds:{bookmaker}" if bookmaker else "odds",
                    prediction_age_seconds=selection_age_seconds,
                    selection_age_seconds=selection_age_seconds,
                    odds_freshness_seconds=odds_freshness_seconds,
                    data_age_seconds=data_age_seconds,
                    source_ok=source_ok,
                    model_drift_flag=model_drift_flag,
                    is_betslip_eligible=is_betslip_eligible,
                    block_reasons=block_reasons,
                    confidence_band=_normalize_live_confidence_band(edge_pct, selection_age_seconds),
                )
            )

    candidates.sort(key=lambda value: value.edge, reverse=True)

    if LIVE_VALUE_MAX_CANDIDATES > 0:
        return candidates[:LIVE_VALUE_MAX_CANDIDATES]
    return candidates


async def _load_live_prediction_map(
    db: AsyncSession, match_ids: list[int], user: User
) -> dict[int, list[ModelPrediction]]:
    if not match_ids:
        return {}

    run_stmt = (
        select(PredictionRun)
        .where(PredictionRun.user_id == user.id, PredictionRun.status == "completed")
        .order_by(PredictionRun.created_at.desc())
        .limit(1)
    )
    run_result = await db.execute(run_stmt)
    run = run_result.scalar_one_or_none()
    if not run:
        return {}

    prediction_stmt = (
        select(ModelPrediction)
        .where(ModelPrediction.run_id == run.id, ModelPrediction.match_id.in_(match_ids))
    )
    prediction_result = await db.execute(prediction_stmt)
    mapped: dict[int, list[ModelPrediction]] = {}
    for prediction in prediction_result.scalars().all():
        mapped.setdefault(prediction.match_id, []).append(prediction)

    return mapped


def _build_match_payload(
    match: Match,
    now: datetime,
    bridge_ready: bool,
    prediction_candidates: list[ModelPrediction] | None = None,
    min_edge: float = 0,
) -> tuple[LiveMatchResponse, datetime | None]:
    source = "oddsharvester"
    source_entry = next((item for item in match.sources if isinstance(item, MatchSource) and item.source), None)
    if source_entry:
        source = source_entry.source

    latest_stat = _latest_record(match.stats)
    momentum, momentum_intensity = _build_momentum(latest_stat)
    selected_odds = _select_bookmaker_odds(list(match.odds))
    live_1x2_odds = [
        entry for entry in list(match.odds) if _normalize_live_market(entry.market) in LIVE_1X2_MARKET_ALIASES
    ]
    match_status = _normalize_match_status(match.status)
    is_live_match = match_status in LIVE_ACTIVE_STATUSES
    freshest_live_odds_timestamp = _safe_max_datetime(
        [odds.timestamp or odds.created_at for odds in live_1x2_odds]
    )

    match_last_update = _safe_max_datetime(
        [
            match.updated_at,
            match.created_at,
            freshest_live_odds_timestamp,
            latest_stat.created_at if latest_stat else None,
        ]
    )
    odds_freshness_seconds = _age_seconds(freshest_live_odds_timestamp, now)
    match_data_age_seconds = _age_seconds(match_last_update, now)
    source_ok = bridge_ready and is_live_match and freshest_live_odds_timestamp is not None

    live_value_candidates = []
    if prediction_candidates:
        live_value_candidates = _build_live_value_candidates(
            match=match,
            predictions=prediction_candidates,
            now=now,
            min_edge=min_edge,
            bridge_ready=bridge_ready,
        )

    payload = LiveMatchResponse.model_validate(
        {
            **match.__dict__,
            "minute": _resolve_match_minute(match, now),
            "momentum": momentum,
            "momentum_intensity": momentum_intensity,
            "source": source,
            "is_live_data": is_live_match,
            "source_ok": source_ok,
            "data_age_seconds": match_data_age_seconds,
            "odds_freshness_seconds": odds_freshness_seconds,
            "has_live_1x2_odds": bool(live_1x2_odds),
            "xg_home": latest_stat.home_xg if latest_stat else None,
            "xg_away": latest_stat.away_xg if latest_stat else None,
            "possession_home": latest_stat.possession_home if latest_stat else None,
            "possession_away": latest_stat.possession_away if latest_stat else None,
            "shots_home": latest_stat.shots_home if latest_stat else None,
            "shots_away": latest_stat.shots_away if latest_stat else None,
            "last_updated_at": match_last_update,
            "live_value_candidates": live_value_candidates,
            "odds": [
                {
                    "id": entry.id,
                    "match_id": entry.match_id,
                    "bookmaker": entry.bookmaker,
                    "market": entry.market,
                    "home_odds": entry.home_odds,
                    "draw_odds": entry.draw_odds,
                    "away_odds": entry.away_odds,
                    "timestamp": entry.timestamp,
                    "created_at": entry.created_at,
                }
                for entry in selected_odds
            ],
        }
    )

    return payload, match_last_update


def _is_bridge_ready() -> tuple[bool, list[str]]:
    issues = get_settings().provider_validation_issues("oddsharvester")
    return len(issues) == 0, issues


def _source_from_bridge_readiness() -> str:
    ready, issues = _is_bridge_ready()
    if ready and not issues:
        return "oddsharvester"
    return "cache"


@router.get("/heartbeat", response_model=LiveHeartbeatResponse)
async def live_heartbeat(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    bridge_ready, bridge_issues = _is_bridge_ready()

    running_jobs_query = select(func.count()).select_from(ScrapeJob).where(ScrapeJob.status == "running")
    result = await db.execute(running_jobs_query)
    jobs_active = int(result.scalar_one() or 0)

    latest_job_query = (
        select(func.max(ScrapeJob.completed_at))
        .where(ScrapeJob.status == "completed")
        .where(ScrapeJob.completed_at.is_not(None))
    )
    latest_completed_result = await db.execute(latest_job_query)
    last_success = latest_completed_result.scalar_one_or_none()

    now = _safe_now()
    source = _source_from_bridge_readiness()
    return LiveHeartbeatResponse(
        schema_version="live-v1",
        jobs_active=jobs_active,
        bridge_ready=bridge_ready,
        bridge_issues=bridge_issues,
        timestamp=now.isoformat(),
        last_success=last_success.isoformat() if last_success else None,
        source=source,
    )


@router.get("/overview", response_model=LiveOverviewResponse)
async def live_overview(
    status: str | None = Query(default="live"),
    league: str | None = Query(default=None),
    max_matches: int = Query(default=50, ge=1, le=200),
    min_live_value_edge: float = Query(default=0, ge=-100, le=100),
    include_live_value: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bridge_ready, _bridge_issues = _is_bridge_ready()
    now = _safe_now()
    source = _source_from_bridge_readiness()

    stmt = (
        select(Match)
        .options(
            selectinload(Match.odds),
            selectinload(Match.sources),
            selectinload(Match.stats),
        )
    )

    is_live_filter = False

    if status and status != "all":
        normalized = status.lower()
        if normalized == "live":
            is_live_filter = True
            stmt = stmt.where(
                Match.status.in_(list(LIVE_ACTIVE_STATUSES))
            )
        elif normalized in {"finished", "ft"}:
            stmt = stmt.where(Match.status.in_(list(LIVE_FINISHED_STATUSES)))
        else:
            stmt = stmt.where(Match.status == normalized)

    if league:
        stmt = stmt.where(Match.competition.ilike(f"%{league}%"))

    if is_live_filter:
        stmt = stmt.order_by(Match.updated_at.desc(), Match.match_date.desc())
    else:
        stmt = stmt.order_by(Match.match_date.asc(), Match.updated_at.desc())

    stmt = stmt.limit(max_matches)

    result = await db.execute(stmt)
    matches = result.scalars().all()

    predictions_by_match: dict[int, list[ModelPrediction]] = {}
    if include_live_value and matches:
        predictions_by_match = await _load_live_prediction_map(
            db=db,
            match_ids=[match.id for match in matches],
            user=user,
        )

    prepared = []
    all_timestamps: list[datetime] = []

    for match in matches:
        if include_live_value:
            match_predictions = predictions_by_match.get(match.id, [])
            live_match, match_last_update = _build_match_payload(
                match,
                now,
                bridge_ready=bridge_ready,
                prediction_candidates=match_predictions,
                min_edge=min_live_value_edge,
            )
        else:
            live_match, match_last_update = _build_match_payload(
                match,
                now,
                bridge_ready=bridge_ready,
            )
        prepared.append(live_match)
        if match_last_update:
            all_timestamps.append(match_last_update)

    freshest = max(all_timestamps) if all_timestamps else None
    data_age_seconds = int((now - freshest).total_seconds()) if freshest else None
    is_data_stale = freshest is None or (data_age_seconds is not None and data_age_seconds > LIVE_STALE_SECONDS)
    jobs_active_result = await db.execute(select(func.count()).select_from(ScrapeJob).where(ScrapeJob.status == "running"))
    jobs_active = int(jobs_active_result.scalar_one() or 0)

    return LiveOverviewResponse(
        matches=prepared,
        source=source,
        is_demo=not bridge_ready,
        generated_at=now.isoformat(),
        data_age_seconds=data_age_seconds,
        is_data_stale=is_data_stale,
        jobs_active=jobs_active,
    )


# Connection manager for active WebSocket clients
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._subscriptions: dict[WebSocket, set[str]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _normalize_channels(raw_channels: Any) -> set[str]:
        if raw_channels is None:
            return {"all"}

        if isinstance(raw_channels, str):
            candidates = [raw_channels]
        elif isinstance(raw_channels, list):
            candidates = raw_channels
        else:
            raise ValueError("Channels must be a string or list of strings")

        normalized: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, str):
                raise ValueError("Channels must only contain strings")
            value = candidate.strip().lower()
            if not value:
                raise ValueError("Channel names cannot be empty")
            normalized.add(value)

        return normalized or {"all"}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
            self._subscriptions[websocket] = {"all"}

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            self._subscriptions.pop(websocket, None)

    async def set_subscriptions(self, websocket: WebSocket, raw_channels: Any) -> list[str]:
        channels = self._normalize_channels(raw_channels)
        async with self._lock:
            if websocket not in self.active_connections:
                raise ValueError("WebSocket is not connected")
            self._subscriptions[websocket] = channels
            return sorted(channels)

    async def get_subscriptions(self, websocket: WebSocket) -> list[str]:
        async with self._lock:
            return sorted(self._subscriptions.get(websocket, {"all"}))

    async def broadcast(self, message: dict[str, Any], *, channel: str = "all", match_id: int | None = None):
        disconnected = []
        normalized_channel = channel.strip().lower()
        async with self._lock:
            connections = [
                conn
                for conn in self.active_connections
                if self._should_receive(
                    self._subscriptions.get(conn, {"all"}),
                    channel=normalized_channel,
                    match_id=match_id,
                )
            ]
        for conn in connections:
            try:
                await conn.send_text(json.dumps(message))
            except Exception:
                disconnected.append(conn)
        async with self._lock:
            for d in disconnected:
                if d in self.active_connections:
                    self.active_connections.remove(d)
                self._subscriptions.pop(d, None)

    @staticmethod
    def _should_receive(subscriptions: set[str], *, channel: str, match_id: int | None) -> bool:
        if "all" in subscriptions or channel in subscriptions:
            return True
        if match_id is not None and f"match:{match_id}" in subscriptions:
            return True
        return False


manager = ConnectionManager()


@router.websocket("/ws")
async def live_websocket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and listen for client messages
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action")
                if action == "subscribe":
                    raw_channels = msg.get("channels", msg.get("channel", "all"))
                    subscriptions = await manager.set_subscriptions(websocket, raw_channels)
                    await websocket.send_text(json.dumps({"type": "subscribed", "channels": subscriptions}))
                elif action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                else:
                    await websocket.send_text(json.dumps({"type": "error", "message": f"Unknown action: {action}"}))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
            except ValueError as exc:
                await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


async def broadcast_odds_update(match_id: int, odds: dict[str, Any]):
    """Broadcast odds update to all connected clients."""
    await manager.broadcast(
        {
            "type": "odds_update",
            "match_id": match_id,
            "data": odds,
            "timestamp": asyncio.get_event_loop().time(),
        },
        channel="odds",
        match_id=match_id,
    )


async def broadcast_prediction_update(run_id: int, status: str, progress: float | None = None):
    """Broadcast prediction run status update."""
    await manager.broadcast(
        {
            "type": "prediction_update",
            "run_id": run_id,
            "status": status,
            "progress": progress,
            "timestamp": asyncio.get_event_loop().time(),
        },
        channel="predictions",
    )


async def broadcast_match_update(match_id: int, event: str, data: dict[str, Any]):
    """Broadcast match event (goal, card, substitution, etc.)."""
    await manager.broadcast(
        {
            "type": "match_event",
            "match_id": match_id,
            "event": event,
            "data": data,
            "timestamp": asyncio.get_event_loop().time(),
        },
        channel="matches",
        match_id=match_id,
    )
