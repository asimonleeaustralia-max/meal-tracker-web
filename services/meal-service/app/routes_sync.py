"""Unified incremental sync — one call returns meals, people, and photos."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from mealtracker_shared.schemas import SyncChangesResponse

from .deps import current_user_id, get_db
from .routes_meals import list_meals, list_people
from .routes_photos import list_photos

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/changes", response_model=SyncChangesResponse)
async def get_sync_changes(
    since: datetime = Query(
        ...,
        description="ISO 8601 cursor — return rows changed at or after this time.",
    ),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> SyncChangesResponse:
    """Incremental pull for all syncable entities in a single request."""
    meals = await list_meals(since=since, limit=1000, offset=0, db=db, user_id=user_id)
    people = await list_people(since=since, db=db, user_id=user_id)
    photos = await list_photos(since=since, limit=2000, offset=0, db=db, user_id=user_id)
    return SyncChangesResponse(
        meals=meals,
        people=people,
        photos=photos,
        server_time=datetime.now(UTC),
    )
