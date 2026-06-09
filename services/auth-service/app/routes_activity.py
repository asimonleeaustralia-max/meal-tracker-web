"""Client-reported activity events (page views, heartbeats, logout)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from mealtracker_shared.schemas import ActivityEventIn

from .activity import client_ip, end_session, record_event
from .deps import current_user_id, get_db

router = APIRouter(prefix="/auth", tags=["activity"])

_ALLOWED_EVENTS = frozenset({
    "page_view",
    "tab_switch",
    "language_change",
    "heartbeat",
    "logout",
    "meal_saved",
    "photo_uploaded",
    "data_export",
})


@router.post("/activity", status_code=204, response_class=Response)
async def post_activity(
    payload: ActivityEventIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> Response:
    if payload.event_type in _ALLOWED_EVENTS:
        if payload.event_type == "logout" and payload.session_id is not None:
            await end_session(db, payload.session_id, user_id)

        await record_event(
            db=db,
            user_id=user_id,
            session_id=payload.session_id,
            event_type=payload.event_type,
            path=payload.path,
            ip_address=client_ip(request),
            language=payload.language,
            bytes_saved=payload.bytes_saved,
            metadata=payload.metadata,
        )
    return Response(status_code=204)
