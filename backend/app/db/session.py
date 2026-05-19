from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_async_engine():
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        future=True,
    )


@lru_cache
def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_async_engine(),
        expire_on_commit=False,
        autoflush=False,
        class_=AsyncSession,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    SessionLocal = get_async_sessionmaker()
    async with SessionLocal() as session:
        yield session


# Sync engine for Celery workers and Alembic
@lru_cache
def get_sync_engine():
    settings = get_settings()
    return create_engine(
        settings.sync_database_url,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def get_sync_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_sync_engine(), expire_on_commit=False, autoflush=False)
