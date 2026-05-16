import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from openforce.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()

# Use NullPool under pytest to avoid asyncpg event-loop-reuse errors between tests.
_engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}
if "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("OPENFORCE_NULLPOOL") == "1":
    _engine_kwargs = {"echo": False, "poolclass": NullPool}

engine = create_async_engine(_settings.database_url, **_engine_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
