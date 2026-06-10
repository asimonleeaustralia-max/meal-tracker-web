"""Account management endpoints (deletion, etc.)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from mealtracker_shared.security import TokenPayload

from .account_deletion import delete_user_account
from .config import Settings, get_settings
from .deps import current_user, get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_account(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Permanently delete the authenticated user and all their data."""
    await delete_user_account(db, uuid.UUID(payload.sub), settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
