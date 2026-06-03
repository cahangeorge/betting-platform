"""Async SQLAlchemy engine + session factory."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()
_driver = str(_settings.database_url)

# SQLite needs check_same_thread=False for async
connect_args = {"check_same_thread": False} if _driver.startswith("sqlite") else {}

engine = create_async_engine(_driver, pool_pre_ping=True, echo=_settings.debug, connect_args=connect_args)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)