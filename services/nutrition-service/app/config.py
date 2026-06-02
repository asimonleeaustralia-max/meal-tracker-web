from __future__ import annotations

from functools import lru_cache

from mealtracker_shared.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "nutrition-service"
    db_schema: str = "nutrition"

    # Fuzzy-match threshold (0-100). Below this we return a miss.
    match_threshold: int = 70

    # Optional: Open Food Facts fallback for products not in our local DB
    enable_openfoodfacts_fallback: bool = True
    openfoodfacts_base_url: str = "https://world.openfoodfacts.org"


@lru_cache
def get_settings() -> Settings:
    return Settings()
