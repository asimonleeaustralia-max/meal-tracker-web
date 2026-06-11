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

    apple_client_id: str = ""  # Apple Services ID (web OAuth)
    apple_ios_client_id: str = ""  # iOS bundle ID (native token-exchange audience)
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

    # Login brute-force protection
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    # Password reset
    password_reset_token_hours: int = 1
    password_reset_base_url: str = "http://localhost:3000"
    password_reset_max_requests_per_hour: int = 3

    # --- Photo storage (for account-deletion blob cleanup) ---
    blob_account_url: str = ""
    blob_container: str = "meal-photos"
    blob_account_key: str = ""

    # SMTP (optional — reset links are logged when unset)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
