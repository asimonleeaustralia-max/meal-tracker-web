"""Brute-force protection for local login."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import LoginAttempt


async def check_login_allowed(
    db: AsyncSession,
    *,
    email: str,
    ip_address: str | None,
    max_attempts: int,
    lockout_minutes: int,
) -> None:
    """Raise 429 if too many recent failed attempts for this email or IP."""
    if max_attempts <= 0:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lockout_minutes)
    normalized_email = email.strip().lower()

    email_count = await db.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.email == normalized_email,
            LoginAttempt.failed_at >= cutoff,
        )
    )
    if email_count and email_count >= max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Try again in {lockout_minutes} minutes or reset your password.",
        )

    if ip_address:
        ip_count = await db.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(
                LoginAttempt.ip_address == ip_address,
                LoginAttempt.failed_at >= cutoff,
            )
        )
        ip_limit = max(max_attempts * 3, max_attempts)
        if ip_count and ip_count >= ip_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed login attempts from this network. Try again in {lockout_minutes} minutes.",
            )


async def record_failed_login(
    db: AsyncSession,
    *,
    email: str,
    ip_address: str | None,
) -> None:
    db.add(
        LoginAttempt(
            email=email.strip().lower(),
            ip_address=ip_address,
            failed_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()


async def clear_login_attempts(
    db: AsyncSession,
    *,
    email: str,
    ip_address: str | None,
) -> None:
    normalized_email = email.strip().lower()
    await db.execute(
        delete(LoginAttempt).where(LoginAttempt.email == normalized_email)
    )
    if ip_address:
        await db.execute(
            delete(LoginAttempt).where(LoginAttempt.ip_address == ip_address)
        )
    await db.flush()
