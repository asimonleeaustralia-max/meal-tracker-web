from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from mealtracker_shared.logging import configure_logging

from .config import get_settings
from .routes_vision import router as vision_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log = configure_logging(settings.service_name, settings.log_level)
    if not settings.runpod_endpoint_url:
        log.warning(
            "RUNPOD_ENDPOINT_URL not set — running in stub mode (returns canned predictions)"
        )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="MealTracker Vision Service", version="0.1.0", lifespan=lifespan)
    app.include_router(vision_router)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    return app


app = create_app()
