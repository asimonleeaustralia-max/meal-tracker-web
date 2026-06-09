"""Password reset token helpers."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import PasswordResetToken, User


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_reset_token() -> tuple[str, str]:
    """Return (plain token for the email link, hash to store)."""
    plain = secrets.token_urlsafe(32)
    return plain, _hash_token(plain)


async def create_reset_token(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    hours_valid: int,
) -> str:
    plain, token_hash = new_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=hours_valid),
        )
    )
    await db.flush()
    return plain


async def count_recent_reset_requests(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    hours: int = 1,
) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    count = await db.scalar(
        select(func.count())
        .select_from(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.created_at >= cutoff,
        )
    )
    return int(count or 0)


async def consume_reset_token(
    db: AsyncSession,
    *,
    token: str,
) -> User:
    token_hash = _hash_token(token)
    row = await db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link",
        )
    now = datetime.now(timezone.utc)
    if row.used_at is not None or row.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link",
        )

    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link",
        )

    row.used_at = now
    await db.flush()
    return user
