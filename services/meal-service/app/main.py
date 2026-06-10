from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from mealtracker_shared.db import Base, Database
from mealtracker_shared.logging import configure_logging

from .config import get_settings
from .deps import init_db
from .routes_meals import people_router, router as meals_router
from .routes_photos import router as photos_router
from .routes_sync import router as sync_router


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
    async with db.engine.begin() as conn:
        if settings.environment == "development":
            await conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"')
            await conn.run_sync(Base.metadata.create_all)
            # Idempotent column adds for inline-photo storage (introduced after initial schema)
            await conn.exec_driver_sql(
                f'ALTER TABLE "{settings.db_schema}".meal_photos '
                'ADD COLUMN IF NOT EXISTS image_data_b64 TEXT'
            )
            await conn.exec_driver_sql(
                f'ALTER TABLE "{settings.db_schema}".meal_photos '
                'ADD COLUMN IF NOT EXISTS thumb_data_b64 TEXT'
            )
            await conn.exec_driver_sql(
                f'ALTER TABLE "{settings.db_schema}".meal_photos '
                'ADD COLUMN IF NOT EXISTS display_order INTEGER NOT NULL DEFAULT 0'
            )
            await conn.exec_driver_sql(
                f'ALTER TABLE "{settings.db_schema}".meal_photos '
                'ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()'
            )
        # Soft-delete tombstones + photo sync cursor; idempotent for prod where Alembic may lag.
        for schema in (settings.db_schema, "public"):
            for table in ("meals", "people"):
                await conn.exec_driver_sql(
                    f"""
                    DO $$ BEGIN
                        ALTER TABLE "{schema}".{table}
                            ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
                    EXCEPTION WHEN undefined_table THEN
                        NULL;
                    END $$;
                    """
                )
            await conn.exec_driver_sql(
                f"""
                DO $$ BEGIN
                    ALTER TABLE "{schema}".meal_photos
                        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
                EXCEPTION WHEN undefined_table THEN
                    NULL;
                END $$;
                """
            )

    init_db(db)
    yield
    await db.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="MealTracker Meal Service", version="0.1.0", lifespan=lifespan)
    app.include_router(meals_router)
    app.include_router(people_router)
    app.include_router(photos_router)
    app.include_router(sync_router)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    return app


app = create_app()
