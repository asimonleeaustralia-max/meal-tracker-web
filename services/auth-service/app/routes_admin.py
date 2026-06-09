"""Admin analytics dashboard API (restricted to admin_email)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mealtracker_shared.schemas import (
    ActivityEventOut,
    AdminOverview,
    AdminUserStats,
    LoginSessionOut,
)

from mealtracker_shared.security import TokenPayload

from .admin_access import is_admin_user
from .config import Settings, get_settings
from .deps import current_user, current_user_id, get_db
from .models import ActivityEvent, LoginSession, User

router = APIRouter(prefix="/auth/admin", tags=["admin"])


async def _require_admin(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    user = await db.get(User, uuid.UUID(payload.sub))
    if user is None or not is_admin_user(
        user,
        token_email=payload.email,
        admin_email=settings.admin_email,
        admin_emails=settings.admin_emails,
        admin_user_ids=settings.admin_user_ids,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


@router.get("/check")
async def admin_check(_admin: User = Depends(_require_admin)) -> dict[str, bool]:
    return {"is_admin": True}


@router.get("/overview", response_model=AdminOverview)
async def admin_overview(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(_require_admin),
) -> AdminOverview:
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)

    total_users = await db.scalar(select(func.count()).select_from(User)) or 0
    total_logins = await db.scalar(select(func.count()).select_from(LoginSession)) or 0
    total_events = await db.scalar(select(func.count()).select_from(ActivityEvent)) or 0
    active_sessions = await db.scalar(
        select(func.count())
        .select_from(LoginSession)
        .where(LoginSession.logged_out_at.is_(None))
    ) or 0
    unique_ips = await db.scalar(
        select(func.count(func.distinct(LoginSession.ip_address)))
        .select_from(LoginSession)
        .where(LoginSession.logged_in_at >= since_24h, LoginSession.ip_address.isnot(None))
    ) or 0
    logins_24h = await db.scalar(
        select(func.count())
        .select_from(LoginSession)
        .where(LoginSession.logged_in_at >= since_24h)
    ) or 0
    events_24h = await db.scalar(
        select(func.count())
        .select_from(ActivityEvent)
        .where(ActivityEvent.created_at >= since_24h)
    ) or 0

    return AdminOverview(
        total_users=total_users,
        total_logins=total_logins,
        total_activity_events=total_events,
        active_sessions=active_sessions,
        unique_ips_24h=unique_ips,
        logins_24h=logins_24h,
        events_24h=events_24h,
    )


@router.get("/sessions", response_model=list[LoginSessionOut])
async def admin_sessions(
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(_require_admin),
) -> list[LoginSessionOut]:
    rows = (
        await db.execute(
            select(LoginSession, User.email)
            .join(User, User.id == LoginSession.user_id)
            .order_by(LoginSession.logged_in_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        LoginSessionOut(
            id=s.id,
            user_id=s.user_id,
            user_email=email,
            login_method=s.login_method,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            language=s.language,
            client=s.client,
            logged_in_at=s.logged_in_at,
            logged_out_at=s.logged_out_at,
            last_seen_at=s.last_seen_at,
            duration_seconds=s.duration_seconds
            or (
                int((s.last_seen_at - s.logged_in_at).total_seconds())
                if s.last_seen_at and s.logged_out_at is None
                else None
            ),
        )
        for s, email in rows
    ]


@router.get("/activity", response_model=list[ActivityEventOut])
async def admin_activity(
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(_require_admin),
) -> list[ActivityEventOut]:
    rows = (
        await db.execute(
            select(ActivityEvent, User.email)
            .join(User, User.id == ActivityEvent.user_id)
            .order_by(ActivityEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        ActivityEventOut(
            id=e.id,
            user_id=e.user_id,
            user_email=email,
            session_id=e.session_id,
            event_type=e.event_type,
            path=e.path,
            ip_address=e.ip_address,
            language=e.language,
            bytes_saved=e.bytes_saved,
            metadata_json=e.metadata_json,
            created_at=e.created_at,
        )
        for e, email in rows
    ]


@router.get("/users", response_model=list[AdminUserStats])
async def admin_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(_require_admin),
) -> list[AdminUserStats]:
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()

    meal_stats: dict[uuid.UUID, tuple[int, int, int]] = {}
    try:
        result = await db.execute(
            text(
                """
                SELECT m.user_id::text,
                       COUNT(DISTINCT m.id) AS meal_count,
                       COUNT(DISTINCT p.id) AS photo_count,
                       COALESCE(SUM(LENGTH(COALESCE(p.image_data_b64, ''))), 0) AS data_bytes
                FROM meal.meals m
                LEFT JOIN meal.meal_photos p ON p.meal_id = m.id
                GROUP BY m.user_id
                """
            )
        )
        for row in result:
            meal_stats[uuid.UUID(row[0])] = (int(row[1]), int(row[2]), int(row[3]))
    except Exception:
        pass

    out: list[AdminUserStats] = []
    for user in users:
        login_agg = await db.execute(
            select(
                func.count(LoginSession.id),
                func.max(LoginSession.logged_in_at),
                func.coalesce(func.sum(LoginSession.duration_seconds), 0),
            ).where(LoginSession.user_id == user.id)
        )
        login_count, last_login_at, total_session_seconds = login_agg.one()

        last_method_row = await db.execute(
            select(LoginSession.login_method)
            .where(LoginSession.user_id == user.id)
            .order_by(LoginSession.logged_in_at.desc())
            .limit(1)
        )
        last_method = last_method_row.scalar_one_or_none()

        event_count = await db.scalar(
            select(func.count())
            .select_from(ActivityEvent)
            .where(ActivityEvent.user_id == user.id)
        ) or 0

        lang_row = await db.execute(
            select(ActivityEvent.language)
            .where(
                ActivityEvent.user_id == user.id,
                ActivityEvent.language.isnot(None),
                ActivityEvent.event_type == "language_change",
            )
            .order_by(ActivityEvent.created_at.desc())
            .limit(1)
        )
        preferred_language = lang_row.scalar_one_or_none()
        if preferred_language is None:
            lang_row = await db.execute(
                select(LoginSession.language)
                .where(LoginSession.user_id == user.id, LoginSession.language.isnot(None))
                .order_by(LoginSession.logged_in_at.desc())
                .limit(1)
            )
            preferred_language = lang_row.scalar_one_or_none()

        ip_row = await db.execute(
            select(LoginSession.ip_address)
            .where(LoginSession.user_id == user.id, LoginSession.ip_address.isnot(None))
            .order_by(LoginSession.logged_in_at.desc())
            .limit(1)
        )
        last_ip = ip_row.scalar_one_or_none()

        meals, photos, data_bytes = meal_stats.get(user.id, (0, 0, 0))
        out.append(
            AdminUserStats(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                login_count=int(login_count or 0),
                last_login_at=last_login_at,
                last_login_method=last_method,
                total_session_seconds=int(total_session_seconds or 0),
                activity_event_count=int(event_count),
                meal_count=meals,
                photo_count=photos,
                data_bytes_saved=data_bytes,
                preferred_language=preferred_language,
                last_ip=last_ip,
            )
        )
    return out
