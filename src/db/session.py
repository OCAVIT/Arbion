"""
Async SQLAlchemy database session configuration.
Optimized for Supabase/Railway PostgreSQL with connection pooling.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.config import settings

logger = logging.getLogger(__name__)

# Create async engine
# NullPool is recommended for serverless environments (Railway, Supabase Transaction Pooler)
engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
    echo=not settings.is_production,  # SQL logging in dev
    connect_args={
        "statement_cache_size": 0,  # Required for Supabase Transaction Pooler
    },
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.
    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions.
    Use in non-FastAPI contexts (scheduler jobs, startup, etc).
    Usage:
        async with get_db_context() as db:
            result = await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
