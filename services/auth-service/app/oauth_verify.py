"""Verify provider-issued ID tokens (used by the iOS native sign-in flow).

This is the bit you MUST get right in production: do not trust an ID token
just because it parses — verify the signature against the provider's JWKS
and check `iss`, `aud`, `exp`.
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException
from jose import jwt
from jose.exceptions import JWTError

from .config import Settings

_JWKS_CACHE: dict[str, dict[str, Any]] = {}

_PROVIDER_JWKS = {
    "google": "https://www.googleapis.com/oauth2/v3/certs",
    "apple": "https://appleid.apple.com/auth/keys",
    # Facebook ID tokens (Limited Login on iOS) use this JWKS:
    "facebook": "https://www.facebook.com/.well-known/oauth/openid/jwks/",
}

_PROVIDER_ISS = {
    "google": ["https://accounts.google.com", "accounts.google.com"],
    "apple": ["https://appleid.apple.com"],
    "facebook": ["https://www.facebook.com"],
}


async def _get_jwks(provider: str) -> dict[str, Any]:
    if provider in _JWKS_CACHE:
        return _JWKS_CACHE[provider]
    url = _PROVIDER_JWKS[provider]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    jwks = resp.json()
    _JWKS_CACHE[provider] = jwks
    return jwks


def _audience_for(provider: str, settings: Settings) -> str | list[str]:
    if provider == "google":
        # Google iOS client ID is also valid audience. List both web + iOS if
        # you have separate ones.
        return settings.google_client_id
    if provider == "apple":
        # Native iOS tokens use the bundle ID; web tokens use the Services ID.
        ids = [x for x in (settings.apple_ios_client_id, settings.apple_client_id) if x]
        if not ids:
            return ""
        return ids[0] if len(ids) == 1 else ids
    if provider == "facebook":
        return settings.facebook_client_id
    raise HTTPException(status_code=404, detail="Unknown provider")


async def verify_provider_id_token(
    *, provider: str, id_token: str, settings: Settings
) -> dict[str, Any]:
    if provider not in _PROVIDER_JWKS:
        raise HTTPException(status_code=404, detail="Unknown provider")

    jwks = await _get_jwks(provider)
    try:
        unverified_header = jwt.get_unverified_header(id_token)
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Malformed id_token: {e}") from e

    kid = unverified_header.get("kid")
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key is None:
        # JWKS may have rotated — clear cache and retry once
        _JWKS_CACHE.pop(provider, None)
        jwks = await _get_jwks(provider)
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key is None:
        raise HTTPException(status_code=401, detail="Signing key not found")

    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=[key.get("alg", "RS256")],
            audience=_audience_for(provider, settings),
            issuer=_PROVIDER_ISS[provider],
            options={"require_exp": True, "require_iat": True},
        )
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid id_token: {e}") from e
    if "sub" not in claims:
        raise HTTPException(status_code=401, detail="id_token missing sub")
    return claims
