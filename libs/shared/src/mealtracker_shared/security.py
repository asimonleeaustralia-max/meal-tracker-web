"""JWT issuing and verification.

`auth-service` is the only service that *issues* tokens.
All other services (and the gateway) only *verify* them.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel


class TokenPayload(BaseModel):
    sub: str             # user UUID as string
    email: str | None = None
    iat: int
    exp: int
    iss: str
    jti: str
    typ: str = "access"  # "access" | "refresh"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_access_token(
    *,
    user_id: uuid.UUID,
    email: str | None,
    secret: str,
    algorithm: str = "HS256",
    issuer: str = "mealtracker-auth",
    minutes: int = 60,
) -> str:
    now = _now()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "iss": issuer,
        "jti": str(uuid.uuid4()),
        "typ": "access",
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def issue_refresh_token(
    *,
    user_id: uuid.UUID,
    secret: str,
    algorithm: str = "HS256",
    issuer: str = "mealtracker-auth",
    days: int = 30,
) -> str:
    now = _now()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=days)).timestamp()),
        "iss": issuer,
        "jti": str(uuid.uuid4()),
        "typ": "refresh",
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def verify_token(
    token: str,
    *,
    secret: str,
    algorithm: str = "HS256",
    issuer: str = "mealtracker-auth",
    expected_type: str = "access",
) -> TokenPayload:
    try:
        decoded = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            issuer=issuer,
            options={"require_exp": True, "require_iat": True},
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        ) from e
    payload = TokenPayload(**decoded)
    if payload.typ != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Wrong token type: expected {expected_type}, got {payload.typ}",
        )
    return payload


# --- FastAPI dependency: extract current user from `Authorization: Bearer …` ---

_bearer = HTTPBearer(auto_error=False)


def get_current_user_dep(secret_getter, issuer: str = "mealtracker-auth"):
    """Build a FastAPI dependency that validates the bearer token.

    `secret_getter` is a callable returning the JWT secret (so each service
    can wire it to its own Settings object).
    """

    async def _dep(
        creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> TokenPayload:
        if creds is None or creds.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return verify_token(creds.credentials, secret=secret_getter(), issuer=issuer)

    return _dep
