"""Delete all user-owned data across auth and meal schemas + Azure blobs."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import (
    ActivityEvent,
    LoginAttempt,
    LoginSession,
    OAuthIdentity,
    PasswordResetToken,
    RefreshToken,
    User,
)

log = logging.getLogger(__name__)


async def _delete_meal_data(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Remove rows in the meal schema owned by this user."""
    params = {"uid": user_id}
    await db.execute(text("DELETE FROM meal.meal_photos WHERE user_id = :uid"), params)
    await db.execute(text("DELETE FROM meal.meals WHERE user_id = :uid"), params)
    await db.execute(text("DELETE FROM meal.people WHERE user_id = :uid"), params)


def _delete_user_blobs(user_id: uuid.UUID, settings: Settings) -> None:
    """Delete Azure blobs under ``{user_id}/``. No-op when blob creds are unset."""
    if not settings.blob_account_url or not settings.blob_account_key:
        return

    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError:
        log.warning("azure-storage-blob not installed; skipping blob deletion")
        return

    prefix = f"{user_id}/"
    try:
        client = BlobServiceClient(
            account_url=settings.blob_account_url,
            credential=settings.blob_account_key,
        )
        container = client.get_container_client(settings.blob_container)
        for blob in container.list_blobs(name_starts_with=prefix):
            container.delete_blob(blob.name)
    except Exception:
        log.exception("Failed to delete blobs for user %s", user_id)
        raise


async def delete_user_account(
    db: AsyncSession,
    user_id: uuid.UUID,
    settings: Settings,
) -> None:
    """Permanently delete a user and all associated data."""
    user = await db.get(User, user_id)
    if user is None:
        return

    # Revoke refresh tokens before removing the user row.
    await db.execute(
        update(RefreshToken).where(RefreshToken.user_id == user_id).values(revoked=True)
    )

    await _delete_meal_data(db, user_id)
    _delete_user_blobs(user_id, settings)

    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    await db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
    await db.execute(delete(ActivityEvent).where(ActivityEvent.user_id == user_id))
    if user.email:
        await db.execute(delete(LoginAttempt).where(LoginAttempt.email == user.email))
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
    await db.execute(delete(OAuthIdentity).where(OAuthIdentity.user_id == user_id))
    await db.delete(user)
