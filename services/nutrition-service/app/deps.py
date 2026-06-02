from __future__ import annotations

import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from mealtracker_shared.db import Database
from mealtracker_shared.security import TokenPayload, get_current_user_dep

from .config import get_settings

_db: Database | None = None


def init_db(db: Database) -> None:
    global _db
    _db = db


async def get_db() -> AsyncSession:
    assert _db is not None
    async for s in _db.dependency():
        yield s


def _secret() -> str:
    return get_settings().jwt_secret


current_user = get_current_user_dep(_secret, issuer=get_settings().jwt_issuer)


async def current_user_id(payload: TokenPayload = Depends(current_user)) -> uuid.UUID:
    return uuid.UUID(payload.sub)
