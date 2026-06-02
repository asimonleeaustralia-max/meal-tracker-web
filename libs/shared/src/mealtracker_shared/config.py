"""Base settings every service inherits.

Each service has its own Settings subclass that adds service-specific fields
and overrides `model_config` with its own env_prefix if needed.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Common config every service needs."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Service identity ---
    service_name: str = "unknown-service"
    environment: str = Field(default="development")  # development | staging | production
    log_level: str = "INFO"

    # --- Database ---
    # Each service writes to its own schema in the same Postgres instance
    # (cheap, simple). Override `db_schema` in each service.
    database_url: str = Field(
        default="postgresql+asyncpg://mealtracker:mealtracker@postgres:5432/mealtracker"
    )
    db_schema: str = "public"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # --- JWT (shared across services so the gateway and downstreams agree) ---
    jwt_secret: str = Field(default="dev-only-change-me")
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60
    jwt_refresh_token_days: int = 30
    jwt_issuer: str = "mealtracker-auth"

    # --- Inter-service URLs (used by api-gateway to route) ---
    auth_service_url: str = "http://auth-service:8001"
    meal_service_url: str = "http://meal-service:8002"
    nutrition_service_url: str = "http://nutrition-service:8003"
    vision_service_url: str = "http://vision-service:8004"
