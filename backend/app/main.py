"""FastAPI application factory."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

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
    from app.api.routes.stats import router as stats_router
    from app.api.routes.health import router as health_router
    from app.api.routes.matches import router as matches_router
    from app.api.routes.predictions import router as predictions_router
    from app.api.routes.training import router as training_router
    from app.api.routes.data import router as data_router

    app.include_router(health_router)
    app.include_router(matches_router, prefix="/api/v1")
    app.include_router(predictions_router, prefix="/api/v1")
    app.include_router(bankroll_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(bot_router, prefix="/api/v1")
    app.include_router(stats_router, prefix="/api/v1")
    app.include_router(training_router, prefix="/api/v1")
    app.include_router(data_router, prefix="/api/v1")

    # Serve SvelteKit frontend (if built)
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend" / "build"
    index_html = frontend_dir / "index.html"

    if frontend_dir.exists() and index_html.exists():
        app.mount("/_app", StaticFiles(directory=str(frontend_dir / "_app")), name="svelte-app")

        @app.get("/{full:path}", response_class=HTMLResponse, include_in_schema=False)
        async def serve_frontend(full: str) -> HTMLResponse:
            if full.startswith("api/") or full in ("docs", "redoc", "openapi.json"):
                return HTMLResponse(status_code=404)
            return HTMLResponse(content=index_html.read_text())

    return app


app = create_application()