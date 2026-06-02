from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from mealtracker_shared.db import Base, Database
from mealtracker_shared.logging import configure_logging

from .config import get_settings
from .deps import init_db
from .routes_lookup import router as lookup_router
from .seed import seed_foods


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.service_name, settings.log_level)

    db = Database(
        settings.database_url,
        schema=settings.db_schema,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
    if settings.environment == "development":
        async with db.engine.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"')
            await conn.run_sync(Base.metadata.create_all)
        async with db.session() as s:
            await seed_foods(s)

    init_db(db)
    yield
    await db.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="MealTracker Nutrition Service", version="0.1.0", lifespan=lifespan)
    app.include_router(lookup_router)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    return app


app = create_app()
