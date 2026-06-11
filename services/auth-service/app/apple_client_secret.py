"""Generate Apple's OAuth client secret (a short-lived ES256 JWT).

Apple's web Sign in with Apple flow requires a JWT client secret signed with
your .p8 private key. See:
https://developer.apple.com/documentation/sign_in_with_apple/generate_and_validate_tokens
"""
from __future__ import annotations

import time

from fastapi import HTTPException
from jose import jwt

from .config import Settings


def generate_apple_client_secret(settings: Settings) -> str:
    """Return a JWT suitable for Authlib's Apple OAuth client_secret."""
    if not settings.apple_client_id:
        raise HTTPException(status_code=503, detail="Apple web sign-in is not configured")
    if not settings.apple_team_id or not settings.apple_key_id or not settings.apple_private_key:
        raise HTTPException(
            status_code=503,
            detail="Apple web sign-in requires APPLE_TEAM_ID, APPLE_KEY_ID, and APPLE_PRIVATE_KEY",
        )

    private_key = settings.apple_private_key.replace("\\n", "\n")
    now = int(time.time())
    headers = {"kid": settings.apple_key_id, "alg": "ES256"}
    claims = {
        "iss": settings.apple_team_id,
        "iat": now,
        "exp": now + 60 * 60 * 24 * 180,  # Apple allows up to 6 months
        "aud": "https://appleid.apple.com",
        "sub": settings.apple_client_id,
    }
    return jwt.encode(claims, private_key, algorithm="ES256", headers=headers)
