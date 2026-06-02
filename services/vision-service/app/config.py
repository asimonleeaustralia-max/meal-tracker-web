from __future__ import annotations

from functools import lru_cache

from mealtracker_shared.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "vision-service"

    # --- RunPod inferencing endpoint ---
    # Serverless endpoint URL, e.g.
    #     https://api.runpod.ai/v2/<endpoint-id>/runsync
    # (use /run for async + /status/<id> polling)
    runpod_endpoint_url: str = ""
    runpod_api_key: str = ""
    runpod_timeout_seconds: float = 60.0
    runpod_async: bool = False  # True → use /run + polling, False → /runsync
    runpod_poll_interval_seconds: float = 1.5
    runpod_max_poll_attempts: int = 40

    # Fail-soft mode for local dev: if no endpoint configured, return a
    # canned response so the rest of the system is exercisable.
    allow_stub_mode: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
