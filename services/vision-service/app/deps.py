from __future__ import annotations

import uuid

from fastapi import Depends

from mealtracker_shared.security import TokenPayload, get_current_user_dep

from .config import get_settings


def _secret() -> str:
    return get_settings().jwt_secret


current_user = get_current_user_dep(_secret, issuer=get_settings().jwt_issuer)


async def current_user_id(payload: TokenPayload = Depends(current_user)) -> uuid.UUID:
    return uuid.UUID(payload.sub)
