"""FastAPI application factory."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.core.database import engine
from app.models.base import metadata as _meta


async def _create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(_meta.create_all)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.debug:
        await _create_tables()
    yield
    await engine.dispose()


def create_application(settings: Settings | None = None) -> FastAPI:
    _settings = settings or get_settings()
    app = FastAPI(
        title=_settings.app_name, version="0.1.0",
        debug=_settings.debug, docs_url="/docs", redoc_url="/redoc",
        lifespan=lifespan,
    )
    from app.api.routes.auth import router as auth_router
    from app.api.routes.bankroll import router as bankroll_router
    from app.api.routes.bot import router as bot_router
    from app.api.routes.health import router as health_router
    from app.api.routes.matches import router as matches_router
    from app.api.routes.predictions import router as predictions_router

    app.include_router(health_router)
    app.include_router(matches_router, prefix="/api/v1")
    app.include_router(predictions_router, prefix="/api/v1")
    app.include_router(bankroll_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(bot_router, prefix="/api/v1")
    return app


app = create_application()