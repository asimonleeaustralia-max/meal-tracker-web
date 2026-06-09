"""Admin access checks."""
from __future__ import annotations

import uuid

from .models import User


def normalize_email(email: str | None) -> str | None:
    """Normalize for comparison (Gmail ignores dots and +tags)."""
    if not email:
        return None
    email = email.strip().lower()
    local, sep, domain = email.partition("@")
    if not sep:
        return email
    if domain in ("gmail.com", "googlemail.com"):
        local = local.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def _parse_admin_emails(raw: str) -> set[str]:
    return {
        n
        for part in raw.split(",")
        if (n := normalize_email(part.strip()))
    }


def _parse_admin_user_ids(raw: str) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(uuid.UUID(part))
        except ValueError:
            continue
    return ids


def is_admin_user(
    user: User | None,
    *,
    token_email: str | None = None,
    admin_email: str = "",
    admin_emails: str = "",
    admin_user_ids: str = "",
) -> bool:
    allowed_emails = _parse_admin_emails(admin_email)
    allowed_emails |= _parse_admin_emails(admin_emails)
    allowed_ids = _parse_admin_user_ids(admin_user_ids)

    if user is not None and user.id in allowed_ids:
        return True

    for email in (
        user.email if user is not None else None,
        token_email,
    ):
        normalized = normalize_email(email)
        if normalized and normalized in allowed_emails:
            return True
    return False
