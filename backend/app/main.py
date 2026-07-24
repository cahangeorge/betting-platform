import warnings
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import v1_router
from app.config import get_settings
from app.database import engine, ensure_dev_admin, ensure_schema
from app.models.user import User
from app.services.python_bridge import bridge_runtime_summary, validate_bridge_runtime
from app.services.scheduled_jobs import start_scheduler, stop_scheduler

settings = get_settings()


class FlexibleCORSMiddleware(BaseHTTPMiddleware):
    """Credentialed CORS restricted to explicitly configured origins."""

    def __init__(self, app: Any, allowed_origins: list[str]):
        super().__init__(app)
        self.allowed_origins = set(allowed_origins)

    def _is_allowed(self, origin: str) -> bool:
        if "*" in self.allowed_origins:
            return True
        if origin in self.allowed_origins:
            return True
        return False

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            origin = request.headers.get("origin", "")
            if self._is_allowed(origin):
                return Response(
                    status_code=204,
                    headers={
                        "Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Credentials": "true",
                        "Access-Control-Allow-Methods": "DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT",
                        "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Requested-With",
                        "Access-Control-Max-Age": "600",
                    },
                )
            return Response(status_code=204)

        response = await call_next(request)
        origin = request.headers.get("origin", "")
        if origin and self._is_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_schema()
    await ensure_dev_admin()

    for issue in validate_bridge_runtime("oddsharvester"):
        warnings.warn(f"OddsHarvester runtime prerequisite issue: {issue}")

    app.state.bridge_runtime = bridge_runtime_summary()
    taskiq_broker = None
    if settings.task_queue_backend == "taskiq":
        from app.tasks.broker import broker

        taskiq_broker = broker
        await taskiq_broker.startup()
    if settings.scheduled_jobs_enabled and settings.task_queue_backend == "inprocess":
        start_scheduler(interval_seconds=settings.scheduled_jobs_interval_seconds)
    try:
        yield
    finally:
        await stop_scheduler()
        if taskiq_broker is not None:
            await taskiq_broker.shutdown()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    FlexibleCORSMiddleware,
    allowed_origins=settings.cors_origin_list,
)

app.include_router(v1_router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}


@app.get("/api/v1/ready", include_in_schema=False)
@app.get("/ready")
async def readiness():
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            try:
                await connection.execute(select(User.id).limit(1))
            except SQLAlchemyError:
                return JSONResponse(
                    status_code=503,
                    content={"status": "unavailable", "database": "ready", "schema": "unavailable"},
                )
    except (OSError, SQLAlchemyError):
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unavailable"},
        )

    response = {"status": "ready", "database": "ready", "schema": "ready"}
    if settings.is_secure_environment and settings.bridge_validation_issues():
        return JSONResponse(
            status_code=503,
            content={
                **response,
                "status": "unavailable",
                "bridge_runtime": "unavailable",
            },
        )
    if settings.is_secure_environment:
        response["bridge_runtime"] = "ready"

    if settings.task_queue_backend == "taskiq":
        from app.tasks.runtime import task_queue_probe, verify_any_runtime_role

        try:
            await task_queue_probe(
                settings.resolved_taskiq_broker_url,
                settings.resolved_taskiq_result_backend_url,
            )
        except (OSError, RuntimeError):
            return JSONResponse(
                status_code=503,
                content={
                    **response,
                    "status": "unavailable",
                    "task_queue": "unavailable",
                },
            )
        try:
            await verify_any_runtime_role("worker")
            await verify_any_runtime_role("scheduler")
        except (OSError, RuntimeError):
            return JSONResponse(
                status_code=503,
                content={
                    **response,
                    "status": "unavailable",
                    "task_queue": "ready",
                    "task_runtime": "unavailable",
                },
            )
        response["task_queue"] = "ready"
        response["task_runtime"] = "ready"

    return response


@app.get("/api/v1/health")
async def api_health():
    return {"status": "ok", "app": settings.app_name}
