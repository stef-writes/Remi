"""Store factory functions — backend selection based on settings.

Postgres-related imports are conditional since ``sqlmodel`` / ``asyncpg``
are optional dependencies (``remi[postgres]``).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from remi.agent.documents.mem import InMemoryDocumentStore
from remi.agent.documents.types import DocumentStore
from remi.domain.portfolio.protocols import PropertyStore
from remi.domain.queries.rollups import RollupStore
from remi.domain.stores.rollups import InMemoryRollupStore, PostgresRollupStore
from remi.types.config import RemiSettings


def build_property_store(
    settings: RemiSettings,
) -> tuple[PropertyStore, AsyncEngine | None, async_sessionmaker[AsyncSession] | None]:
    """Return ``(property_store, db_engine | None, session_factory | None)``.

    The engine and session factory are exposed so the container can share
    them with other Postgres-backed stores and the bootstrap lifecycle.
    """
    from remi.domain.stores.mem import InMemoryPropertyStore

    backend = settings.state_store.backend
    if backend == "postgres":
        dsn = settings.state_store.dsn or settings.secrets.database_url
        if not dsn:
            raise ValueError(
                "state_store.backend is 'postgres' but no DATABASE_URL or "
                "state_store.dsn is configured."
            )
        from remi.agent.db.engine import async_session_factory, create_async_engine_from_url
        from remi.domain.stores.pg import PostgresPropertyStore

        engine = create_async_engine_from_url(dsn)
        session_factory = async_session_factory(engine)
        return PostgresPropertyStore(session_factory), engine, session_factory

    return InMemoryPropertyStore(), None, None


def build_document_store(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> DocumentStore:
    """Return a Postgres or in-memory document store."""
    if session_factory is not None:
        from remi.agent.documents.pg import PostgresDocumentStore

        return PostgresDocumentStore(session_factory)
    return InMemoryDocumentStore()


def build_rollup_store(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> RollupStore:
    """Return a Postgres or in-memory rollup store."""
    if session_factory is not None:
        return PostgresRollupStore(session_factory)
    return InMemoryRollupStore()
