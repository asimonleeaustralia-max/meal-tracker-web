"""Auth-service configuration."""
from __future__ import annotations

from functools import lru_cache

from mealtracker_shared.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "auth-service"
    db_schema: str = "auth"

    # --- OAuth providers ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8080/api/auth/oauth/google/callback"

    apple_client_id: str = ""  # iOS bundle ID or web Services ID
    apple_team_id: str = ""
    apple_key_id: str = ""
    apple_private_key: str = ""  # PEM contents
    apple_redirect_uri: str = "http://localhost:8080/api/auth/oauth/apple/callback"

    facebook_client_id: str = ""
    facebook_client_secret: str = ""
    facebook_redirect_uri: str = "http://localhost:8080/api/auth/oauth/facebook/callback"

    # Where to send the user after a successful OAuth flow
    oauth_success_redirect: str = "http://localhost:3000/auth/success"
    oauth_failure_redirect: str = "http://localhost:3000/auth/failure"

    # Session secret for the short-lived OAuth state cookie
    session_secret: str = "dev-only-session-secret-change-me"

    # Admin dashboard access
    admin_email: str = "asimonlee@gmail.com"
    admin_emails: str = ""  # comma-separated extra admin emails
    admin_user_ids: str = ""  # comma-separated user UUIDs


@lru_cache
def get_settings() -> Settings:
    return Settings()
