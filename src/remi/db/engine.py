"""Async database engine and session factory.

Usage in the container:
    engine = create_async_engine_from_url(settings.secrets.database_url)
    session_factory = async_session_factory(engine)
    await create_tables(engine)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def create_async_engine_from_url(
    database_url: str,
    *,
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
) -> AsyncEngine:
    """Build an async engine from a Postgres DSN.

    Accepts standard ``postgresql://`` URLs and rewrites to
    ``postgresql+asyncpg://`` so callers don't need to know the driver.
    """
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return create_async_engine(
        database_url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
    )


def async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables(engine: AsyncEngine) -> None:
    """Create all SQLModel tables. Safe to call repeatedly (IF NOT EXISTS)."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with factory() as session:
        yield session
