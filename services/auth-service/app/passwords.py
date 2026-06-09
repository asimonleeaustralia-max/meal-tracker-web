"""Password hashing using bcrypt directly.

Why not passlib? passlib's bcrypt backend has compatibility issues with
modern bcrypt 4.x releases (no `__about__` attribute, stricter 72-byte
password limit during its internal detection probe). Calling bcrypt
directly is the official passlib migration path.
"""
from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    # bcrypt's input limit is 72 bytes; we truncate at the encoded length to
    # be safe with multi-byte unicode. This is the standard recommendation;
    # if you ever want to support truly long passphrases, pre-hash with
    # SHA-256 before bcrypt and document that change.
    pw_bytes = plain.encode("utf-8")[:72]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> str | None:
    """Return an error message if the password is too weak, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if len(password) > 72:
        return "Password must be at most 72 characters"
    if not any(c.isupper() for c in password):
        return "Password must include an uppercase letter"
    if not any(c.islower() for c in password):
        return "Password must include a lowercase letter"
    if not any(c.isdigit() for c in password):
        return "Password must include a number"
    if not any(not c.isalnum() for c in password):
        return "Password must include a special character"
    return None
