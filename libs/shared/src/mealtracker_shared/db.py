"""Shared async SQLAlchemy engine + session factory.

Usage in a service:

    from mealtracker_shared.db import Database, Base
    db = Database(settings.database_url, schema=settings.db_schema)
    async with db.session() as s:
        ...
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base every service uses for its ORM models."""


class Database:
    def __init__(
        self,
        url: str,
        *,
        schema: str | None = None,
        pool_size: int = 5,
        max_overflow: int = 10,
        echo: bool = False,
    ) -> None:
        connect_args: dict = {}
        if schema:
            # Bind every connection to the service's schema by default
            connect_args["server_settings"] = {"search_path": f"{schema},public"}

        self._engine: AsyncEngine = create_async_engine(
            url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )
        self.schema = schema

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dependency(self) -> AsyncIterator[AsyncSession]:
        """FastAPI dependency-injection version."""
        async with self.session() as s:
            yield s

    async def dispose(self) -> None:
        await self._engine.dispose()
