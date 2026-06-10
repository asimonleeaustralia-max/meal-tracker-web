"""API gateway.

Public entry point. Maps URL prefixes to internal services:

    /api/auth/*       → auth-service
    /api/meals/*      → meal-service
    /api/people/*     → meal-service
    /api/photos/*     → meal-service
    /api/nutrition/*  → nutrition-service
    /api/vision/*     → vision-service

Behaviour:
  * Strips `/api` from the path before forwarding (downstream services
    expose `/meals`, `/auth`, … directly).
  * Validates the bearer token on every route except auth signup/login/refresh
    and OAuth callbacks. This keeps backends simple: they trust the token if
    it's present and the gateway has signed it off.
  * Streams the response back so even big photo uploads don't buffer.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from mealtracker_shared.logging import configure_logging
from mealtracker_shared.security import verify_token

from .config import get_settings


# ---- Routing table ----

_ROUTES: list[tuple[str, str]] = [
    # (path prefix that the gateway accepts, service URL setting attribute)
    ("/api/auth",      "auth_service_url"),
    ("/api/meals",     "meal_service_url"),
    ("/api/people",    "meal_service_url"),
    ("/api/photos",    "meal_service_url"),
    ("/api/nutrition", "nutrition_service_url"),
    ("/api/vision",    "vision_service_url"),
]

# Endpoints that don't require a JWT (login flows + health)
_PUBLIC_PREFIXES = (
    "/api/auth/signup",
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/oauth",  # browser OAuth start/callback
)


def _resolve_target(path: str, settings) -> tuple[str, str] | None:
    """Return (downstream_base_url, remainder_path) or None if no route matches."""
    for prefix, attr in _ROUTES:
        if path == prefix or path.startswith(prefix + "/"):
            base = getattr(settings, attr)
            remainder = path[len("/api"):]  # strip "/api", keep the rest
            return base, remainder
    return None


def _needs_auth(path: str) -> bool:
    return not any(path.startswith(p) for p in _PUBLIC_PREFIXES)


def create_app() -> FastAPI:
    settings = get_settings()
    log = configure_logging(settings.service_name, settings.log_level)

    app = FastAPI(title="MealTracker API Gateway", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # One shared HTTP client per process. Connection pool keeps inter-service
    # calls snappy.
    _client = httpx.AsyncClient(timeout=settings.request_timeout_seconds)

    @app.on_event("shutdown")
    async def _close_client() -> None:
        await _client.aclose()

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.api_route(
        "/api/{full_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    async def proxy(full_path: str, request: Request) -> Response:
        target = _resolve_target(request.url.path, settings)
        if target is None:
            raise HTTPException(status_code=404, detail="No route")
        base_url, remainder = target

        # Auth check
        if _needs_auth(request.url.path):
            auth_header = request.headers.get("authorization", "")
            if not auth_header.lower().startswith("bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing bearer token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            token = auth_header.split(None, 1)[1]
            # This raises 401 on failure
            verify_token(
                token,
                secret=settings.jwt_secret,
                algorithm=settings.jwt_algorithm,
                issuer=settings.jwt_issuer,
            )

        # Build downstream URL
        qs = request.url.query
        downstream_url = base_url.rstrip("/") + remainder + (f"?{qs}" if qs else "")

        # Strip hop-by-hop headers
        skip = {
            "host", "content-length", "connection", "keep-alive",
            "transfer-encoding", "te", "trailer", "upgrade", "proxy-authorization",
        }
        forward_headers = {
            k: v for k, v in request.headers.items() if k.lower() not in skip
        }

        body = await request.body()

        try:
            rsp = await _client.request(
                method=request.method,
                url=downstream_url,
                headers=forward_headers,
                content=body,
            )
        except httpx.HTTPError as e:
            log.exception("Upstream call failed: %s", downstream_url)
            raise HTTPException(status_code=502, detail=f"Upstream error: {e}") from e

        body_out = rsp.content

        resp_skip = {
            "content-encoding", "transfer-encoding", "connection",
            "content-length", "keep-alive",
        }
        resp_headers = {
            k: v for k, v in rsp.headers.items() if k.lower() not in resp_skip
        }

        return Response(
            content=body_out,
            status_code=rsp.status_code,
            headers=resp_headers,
            media_type=rsp.headers.get("content-type"),
        )

    return app


app = create_app()
