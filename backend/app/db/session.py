from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.logging import get_logger

logger = get_logger(__name__)

SQLITE_FALLBACK = "sqlite+aiosqlite:///./earnings_engine.db"


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def _resolve_url(db_url: str) -> str:
    if db_url.startswith("postgresql") and "aiosqlite" not in db_url:
        try:
            import asyncpg  # noqa: F401
            if "+asyncpg" not in db_url:
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
                db_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
            return db_url
        except ImportError:
            logger.warning(
                "asyncpg_not_available",
                msg="PostgreSQL URL configured but asyncpg not installed. Falling back to SQLite.",
            )
            return SQLITE_FALLBACK
    return db_url


def get_engine():
    global _engine
    if _engine is None:
        from app.core.config import get_settings
        settings = get_settings()
        url = _resolve_url(settings.db.DATABASE_URL)
        _engine = create_async_engine(
            url,
            echo=settings.ENVIRONMENT.value == "local",
        )
        logger.info("db_engine_created", url=url.split("@")[-1] if "@" in url else url)
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    engine = get_engine()
    await engine.dispose()
