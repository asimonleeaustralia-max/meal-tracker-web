"""Activity and login-session recording helpers."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ActivityEvent, LoginSession


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()[:45]
    if request.client is not None:
        return request.client.host[:45]
    return None


async def record_login(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    login_method: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    language: str | None = None,
    client: str = "web",
) -> LoginSession:
    session = LoginSession(
        user_id=user_id,
        login_method=login_method,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:255] or None,
        language=(language or "")[:20] or None,
        client=client,
        logged_in_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()
    return session


async def touch_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    await db.execute(
        update(LoginSession)
        .where(
            LoginSession.id == session_id,
            LoginSession.user_id == user_id,
            LoginSession.logged_out_at.is_(None),
        )
        .values(last_seen_at=datetime.now(timezone.utc))
    )


async def end_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> LoginSession | None:
    session = await db.scalar(
        select(LoginSession).where(
            LoginSession.id == session_id,
            LoginSession.user_id == user_id,
        )
    )
    if session is None or session.logged_out_at is not None:
        return session
    now = datetime.now(timezone.utc)
    session.logged_out_at = now
    session.last_seen_at = now
    delta = now - session.logged_in_at
    session.duration_seconds = max(int(delta.total_seconds()), 0)
    return session


async def record_event(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    event_type: str,
    session_id: uuid.UUID | None = None,
    path: str | None = None,
    ip_address: str | None = None,
    language: str | None = None,
    bytes_saved: int | None = None,
    metadata: dict | None = None,
) -> ActivityEvent:
    if session_id is not None:
        await touch_session(db, session_id, user_id)
    event = ActivityEvent(
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        path=(path or "")[:500] or None,
        ip_address=ip_address,
        language=(language or "")[:20] or None,
        bytes_saved=bytes_saved,
        metadata_json=metadata,
    )
    db.add(event)
    await db.flush()
    return event
