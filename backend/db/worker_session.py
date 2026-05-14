"""
Worker-safe async session factory.

Celery workers run each task in a fresh event loop via _run_async().
The module-level engine in db.session has its connection pool bound to
a different event loop, causing "Future attached to a different loop" errors.

This module provides a fresh engine + session factory per call, so each
Celery task gets connections on the correct event loop.
"""
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from core.config import settings


def create_worker_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create a brand-new engine + session factory for the current event loop."""
    engine = create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        echo=False,
    )
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


@asynccontextmanager
async def get_worker_session():
    """Convenience: create a one-shot session with its own engine."""
    factory = create_worker_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    # Dispose the engine to close the connection pool
    await factory.kw["bind"].dispose()
