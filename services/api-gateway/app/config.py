from __future__ import annotations

from functools import lru_cache

from mealtracker_shared.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "api-gateway"

    # CORS — set to the production web origins
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
    ]

    request_timeout_seconds: float = 75.0  # vision can be slow on cold-start


@lru_cache
def get_settings() -> Settings:
    return Settings()
