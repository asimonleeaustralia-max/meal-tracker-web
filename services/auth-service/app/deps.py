"""FastAPI dependencies for the auth-service."""
from __future__ import annotations

import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from mealtracker_shared.db import Database
from mealtracker_shared.security import (
    TokenPayload,
    get_current_user_dep,
)

from .config import Settings, get_settings

# Single Database instance per process. main.py sets it up at startup.
_db: Database | None = None


def init_db(db: Database) -> None:
    global _db
    _db = db


async def get_db() -> AsyncSession:
    assert _db is not None, "Database not initialised"
    async for s in _db.dependency():
        yield s


def _secret() -> str:
    return get_settings().jwt_secret


# Reusable dependency: any route that wants the current user adds
#     payload: TokenPayload = Depends(current_user)
current_user = get_current_user_dep(_secret, issuer=get_settings().jwt_issuer)


async def current_user_id(payload: TokenPayload = Depends(current_user)) -> uuid.UUID:
    return uuid.UUID(payload.sub)


def get_settings_dep() -> Settings:
    return get_settings()


async def require_admin_user(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> uuid.UUID:
    from fastapi import HTTPException, status

    from .config import get_settings
    from .models import User

    user = await db.get(User, user_id)
    admin_email = get_settings().admin_email.lower()
    if user is None or (user.email or "").lower() != admin_email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user_id
