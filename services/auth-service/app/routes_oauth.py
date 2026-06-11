"""OAuth login flows for Google, Apple, and Facebook.

Each provider follows the same shape:
    GET  /auth/oauth/{provider}/login     → redirect user to provider
    GET  /auth/oauth/{provider}/callback  → handle provider redirect, issue our JWT

The iOS app should use native SDKs (Sign in with Apple, Google Sign-In) and
hit `/auth/oauth/{provider}/token-exchange` with the provider's ID token to
get our JWT back. That endpoint is also scaffolded below.
"""
from __future__ import annotations

import uuid

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mealtracker_shared.schemas import TokenPair

from .config import Settings, get_settings
from .deps import get_db
from .models import OAuthIdentity, User
from .routes_local import _issue_pair

router = APIRouter(prefix="/auth/oauth", tags=["oauth"])


# ----------------------------- OAuth registry -----------------------------

_oauth = OAuth()
_oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
_oauth.register(
    name="apple",
    # Apple's OIDC config (Apple does NOT publish a discovery URL like Google,
    # but its endpoints are documented and stable)
    authorize_url="https://appleid.apple.com/auth/authorize",
    access_token_url="https://appleid.apple.com/auth/token",
    client_kwargs={"scope": "name email", "response_mode": "form_post"},
)
_oauth.register(
    name="facebook",
    authorize_url="https://www.facebook.com/v18.0/dialog/oauth",
    access_token_url="https://graph.facebook.com/v18.0/oauth/access_token",
    api_base_url="https://graph.facebook.com/v18.0/",
    client_kwargs={"scope": "email public_profile"},
)


def _configure_clients(settings: Settings) -> None:
    """Patch Authlib client config at startup with values from Settings."""
    g = _oauth.create_client("google")
    if g is not None:
        g.client_id = settings.google_client_id
        g.client_secret = settings.google_client_secret

    a = _oauth.create_client("apple")
    if a is not None:
        a.client_id = settings.apple_client_id
        # Apple web OAuth uses a JWT client secret — set per-request in login/callback.
        a.client_secret = None

    f = _oauth.create_client("facebook")
    if f is not None:
        f.client_id = settings.facebook_client_id
        f.client_secret = settings.facebook_client_secret


# ----------------------------- Helpers -----------------------------

async def _find_or_create_user_from_oauth(
    *,
    db: AsyncSession,
    provider: str,
    provider_user_id: str,
    email: str | None,
    display_name: str | None,
) -> User:
    """Find a user by (provider, subject); else by email; else create."""
    # 1. Already-linked identity?
    linked = await db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider,
            OAuthIdentity.provider_user_id == provider_user_id,
        )
    )
    if linked is not None:
        user = await db.get(User, linked.user_id)
        if user is not None:
            return user

    # 2. Existing user with same verified email? Link the identity.
    if email is not None:
        existing = await db.scalar(select(User).where(User.email == email))
        if existing is not None:
            db.add(
                OAuthIdentity(
                    user_id=existing.id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    provider_email=email,
                )
            )
            return existing

    # 3. Brand-new user
    user = User(email=email, display_name=display_name)
    db.add(user)
    await db.flush()
    db.add(
        OAuthIdentity(
            user_id=user.id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=email,
        )
    )
    return user


# ----------------------------- Browser redirect flow -----------------------------

def _prepare_oauth_client(provider: str, settings: Settings):
    """Return an Authlib client with provider-specific secrets applied."""
    client = _oauth.create_client(provider)
    if client is None:
        raise HTTPException(status_code=404, detail="Unknown provider")
    if provider == "apple":
        from .apple_client_secret import generate_apple_client_secret

        client.client_secret = generate_apple_client_secret(settings)
    return client


@router.get("/{provider}/login")
async def oauth_login(
    provider: str, request: Request, settings: Settings = Depends(get_settings)
) -> RedirectResponse:
    if provider not in {"google", "apple", "facebook"}:
        raise HTTPException(status_code=404, detail="Unknown provider")
    client = _prepare_oauth_client(provider, settings)
    redirect_uri = {
        "google": settings.google_redirect_uri,
        "apple": settings.apple_redirect_uri,
        "facebook": settings.facebook_redirect_uri,
    }[provider]
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/{provider}/callback")
@router.post("/{provider}/callback")  # Apple uses form_post
async def oauth_callback(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    if provider not in {"google", "apple", "facebook"}:
        raise HTTPException(status_code=404, detail="Unknown provider")
    client = _prepare_oauth_client(provider, settings)
    try:
        token = await client.authorize_access_token(request)
    except OAuthError as e:
        return RedirectResponse(f"{settings.oauth_failure_redirect}?error={e.error}")

    sub: str | None = None
    email: str | None = None
    display_name: str | None = None

    if provider == "google":
        userinfo = token.get("userinfo") or await client.userinfo(token=token)
        sub = userinfo.get("sub")
        email = userinfo.get("email")
        display_name = userinfo.get("name")
    elif provider == "apple":
        # Apple's ID token contains sub + (optionally first-time only) email
        id_token = token.get("id_token")
        claims = await client.parse_id_token(request, token) if id_token else {}
        sub = claims.get("sub")
        email = claims.get("email")
        # Apple sends name only on first login, in the form body
        form = await request.form()
        if "user" in form:
            import json

            try:
                user_info = json.loads(form["user"])
                name = user_info.get("name", {})
                display_name = " ".join(
                    [name.get("firstName", ""), name.get("lastName", "")]
                ).strip() or None
            except json.JSONDecodeError:
                pass
    elif provider == "facebook":
        resp = await client.get("me?fields=id,name,email", token=token)
        data = resp.json()
        sub = data.get("id")
        email = data.get("email")
        display_name = data.get("name")

    if not sub:
        return RedirectResponse(f"{settings.oauth_failure_redirect}?error=no_subject")

    user = await _find_or_create_user_from_oauth(
        db=db,
        provider=provider,
        provider_user_id=sub,
        email=email,
        display_name=display_name,
    )
    pair = await _issue_pair(
        user, settings, db, login_method=provider, request=request, client="web"
    )
    # Hand tokens to the SPA via URL fragment (so they don't hit server logs)
    frag = (
        f"#access_token={pair.access_token}"
        f"&refresh_token={pair.refresh_token}"
        f"&expires_in={pair.expires_in}"
    )
    if pair.session_id is not None:
        frag += f"&session_id={pair.session_id}"
    return RedirectResponse(f"{settings.oauth_success_redirect}{frag}")


# ----------------------------- Native iOS token exchange -----------------------------
# iOS clients should use the native SDKs (Sign in with Apple, GoogleSignIn,
# Facebook Login) and exchange the resulting ID token for our JWT here.

class TokenExchangeRequest(BaseModel):
    """ID token issued by the provider's native SDK."""

    id_token: str
    # Optional, for providers that don't include them in the ID token
    email: str | None = None
    display_name: str | None = None


@router.post("/{provider}/token-exchange", response_model=TokenPair)
async def oauth_token_exchange(
    provider: str,
    payload: TokenExchangeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    """Validate a provider-issued ID token and return our JWT pair."""
    if provider not in {"google", "apple", "facebook"}:
        raise HTTPException(status_code=404, detail="Unknown provider")

    from .oauth_verify import verify_provider_id_token

    claims = await verify_provider_id_token(
        provider=provider, id_token=payload.id_token, settings=settings
    )
    sub = claims["sub"]
    email = payload.email or claims.get("email")
    display_name = payload.display_name or claims.get("name")

    user = await _find_or_create_user_from_oauth(
        db=db,
        provider=provider,
        provider_user_id=sub,
        email=email,
        display_name=display_name,
    )
    return await _issue_pair(
        user, settings, db, login_method=provider, request=request, client="ios"
    )
