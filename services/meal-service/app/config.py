from __future__ import annotations

from functools import lru_cache

from mealtracker_shared.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "meal-service"
    db_schema: str = "meal"

    # --- Photo storage (Azure Blob Storage) ---
    blob_account_url: str = ""        # e.g. https://mealtrackerstg.blob.core.windows.net
    blob_container: str = "meal-photos"
    blob_sas_ttl_minutes: int = 30
    # If using managed identity in prod, leave the key empty
    blob_account_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
