"""auth-service FastAPI entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from mealtracker_shared.db import Base, Database
from mealtracker_shared.logging import configure_logging

from .config import get_settings
from .deps import init_db
from .routes_account import router as account_router
from .routes_activity import router as activity_router
from .routes_admin import router as admin_router
from .routes_local import router as local_router
from .routes_oauth import _configure_clients, router as oauth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log = configure_logging(settings.service_name, settings.log_level)
    log.info(f"Starting {settings.service_name} (env={settings.environment})")

    db = Database(
        settings.database_url,
        schema=settings.db_schema,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
    # Ensure schema and tables exist (create_all is idempotent; alembic for alters).
    async with db.engine.begin() as conn:
        await conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"')
        await conn.run_sync(Base.metadata.create_all)

    init_db(db)
    _configure_clients(settings)

    yield

    await db.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="MealTracker Auth Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)

    app.include_router(local_router)
    app.include_router(account_router)
    app.include_router(oauth_router)
    app.include_router(activity_router)
    app.include_router(admin_router)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    return app


app = create_app()
