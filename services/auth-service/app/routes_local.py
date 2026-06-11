"""Local (email/password) auth endpoints + token refresh."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mealtracker_shared.schemas import TokenPair, UserPublic
from mealtracker_shared.security import (
    TokenPayload,
    issue_access_token,
    issue_refresh_token,
    verify_token,
)

from .admin_access import is_admin_user

from .activity import client_ip, record_login
from .config import Settings, get_settings
from .deps import current_user, current_user_id, get_db
from .email_send import send_password_reset_email
from .login_security import check_login_allowed, clear_login_attempts, record_failed_login
from .models import OAuthIdentity, RefreshToken, User
from .password_reset import consume_reset_token, count_recent_reset_requests, create_reset_token
from .passwords import hash_password, validate_password_strength, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None
    client: Literal["web", "ios"] = "web"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    client: Literal["web", "ios"] = "web"


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


RESET_ACK = (
    "If an account with that email exists, password reset instructions have been sent."
)


async def _issue_pair(
    user: User,
    settings: Settings,
    db: AsyncSession,
    *,
    login_method: str = "local",
    request: Request | None = None,
    language: str | None = None,
    client: str = "web",
) -> TokenPair:
    session = await record_login(
        db=db,
        user_id=user.id,
        login_method=login_method,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent") if request else None,
        language=language,
        client=client,
    )
    access = issue_access_token(
        user_id=user.id,
        email=user.email,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        minutes=settings.jwt_access_token_minutes,
    )
    refresh = issue_refresh_token(
        user_id=user.id,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        days=settings.jwt_refresh_token_days,
    )

    # Persist the refresh JTI so we can revoke it later
    decoded = verify_token(
        refresh,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        expected_type="refresh",
    )
    db.add(
        RefreshToken(
            jti=uuid.UUID(decoded.jti),
            user_id=user.id,
            issued_at=datetime.fromtimestamp(decoded.iat, tz=timezone.utc),
            expires_at=datetime.fromtimestamp(decoded.exp, tz=timezone.utc),
        )
    )

    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_token_minutes * 60,
        session_id=session.id,
    )


@router.post("/signup", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    if err := validate_password_strength(payload.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    # Reject duplicates
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with that email already exists",
        )
    user = User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    await db.flush()
    return await _issue_pair(
        user, settings, db, login_method="local", request=request, client=payload.client
    )


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    ip = client_ip(request)
    await check_login_allowed(
        db,
        email=payload.email,
        ip_address=ip,
        max_attempts=settings.login_max_attempts,
        lockout_minutes=settings.login_lockout_minutes,
    )

    user = await db.scalar(select(User).where(User.email == payload.email))
    if user is None or user.password_hash is None or not verify_password(
        payload.password, user.password_hash
    ):
        await record_failed_login(db, email=payload.email, ip_address=ip)
        # Single generic message so we don't leak which half is wrong
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")

    await clear_login_attempts(db, email=payload.email, ip_address=ip)
    return await _issue_pair(
        user, settings, db, login_method="local", request=request, client=payload.client
    )


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    ip = client_ip(request)
    await check_login_allowed(
        db,
        email=payload.email,
        ip_address=ip,
        max_attempts=settings.login_max_attempts * settings.password_reset_max_requests_per_hour,
        lockout_minutes=60,
    )

    user = await db.scalar(select(User).where(User.email == payload.email))
    if user is not None and user.password_hash is not None and user.is_active:
        recent = await count_recent_reset_requests(db, user_id=user.id)
        if recent < settings.password_reset_max_requests_per_hour:
            plain = await create_reset_token(
                db,
                user_id=user.id,
                hours_valid=settings.password_reset_token_hours,
            )
            base = settings.password_reset_base_url.rstrip("/")
            reset_url = f"{base}/?reset_token={plain}"
            send_password_reset_email(settings, to_email=user.email, reset_url=reset_url)

    return {"message": RESET_ACK}


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    if err := validate_password_strength(payload.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    user = await consume_reset_token(db, token=payload.token)
    user.password_hash = hash_password(payload.password)
    await clear_login_attempts(db, email=user.email or "", ip_address=None)
    return {"message": "Password updated. You can sign in with your new password."}


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    decoded = verify_token(
        payload.refresh_token,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        issuer=settings.jwt_issuer,
        expected_type="refresh",
    )
    stored = await db.get(RefreshToken, uuid.UUID(decoded.jti))
    if stored is None or stored.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked or unknown",
        )
    user = await db.get(User, uuid.UUID(decoded.sub))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User missing")

    # Rotate: revoke the old refresh, issue a new pair
    stored.revoked = True
    return await _issue_pair(user, settings, db)


@router.get("/me", response_model=UserPublic)
async def me(
    db: AsyncSession = Depends(get_db),
    payload: TokenPayload = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> UserPublic:
    user = await db.get(User, uuid.UUID(payload.sub))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    admin = is_admin_user(
        user,
        token_email=payload.email,
        admin_email=settings.admin_email,
        admin_emails=settings.admin_emails,
        admin_user_ids=settings.admin_user_ids,
    )
    identity = await db.scalar(
        select(OAuthIdentity.provider)
        .where(OAuthIdentity.user_id == user.id)
        .order_by(OAuthIdentity.created_at)
        .limit(1)
    )
    provider = identity if identity else ("local" if user.password_hash else "oauth")
    return UserPublic.model_validate(user).model_copy(
        update={"is_admin": admin, "provider": provider}
    )
