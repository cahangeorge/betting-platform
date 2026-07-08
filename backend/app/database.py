from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Base
from app.models.user import User
from app.services.auth import hash_password

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def ensure_schema() -> None:
    if not (settings.auto_create_schema or settings.database_url.startswith("sqlite+")):
        return

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def ensure_dev_admin() -> None:
    if not settings.seed_dev_admin:
        return
    if not settings.database_url.startswith("sqlite+"):
        return

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == settings.dev_admin_email.strip().lower()))
        existing_user = result.scalar_one_or_none()
        if existing_user is not None:
            return

        session.add(
            User(
                email=settings.dev_admin_email.strip().lower(),
                name=settings.dev_admin_name,
                password_hash=hash_password(settings.dev_admin_password),
                is_admin=True,
            )
        )
        await session.commit()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
