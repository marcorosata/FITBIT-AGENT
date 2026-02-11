"""Middleware — CORS, API key authentication, request logging, error handling."""

from __future__ import annotations

import time
from typing import Callable

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from wearable_agent.config import get_settings

logger = structlog.get_logger(__name__)


# ── CORS ──────────────────────────────────────────────────────


def add_cors(app: FastAPI) -> None:
    """Configure CORS from application settings.

    ``settings.cors_origins`` is a comma-separated string of allowed
    origins (or ``"*"`` to allow all).
    """
    settings = get_settings()
    origins_raw = settings.cors_origins.strip()

    if origins_raw == "*":
        origins = ["*"]
    else:
        origins = [o.strip() for o in origins_raw.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )


# ── API key authentication ────────────────────────────────────

_PUBLIC_PATHS: set[str] = {
    "/",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/auth/fitbit",
    "/auth/fitbit/callback",
    "/admin",
    "/app",
    "/api/stats",
    "/system/info",
}

_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/ws/",
    "/static/",
    "/admin/api/",
)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Verify ``X-API-Key`` or ``Authorization: Bearer <key>`` on protected routes.

    Public paths (health, docs, OAuth callbacks, static) are exempt.
    Disabled when ``api_secret_key`` is the default placeholder.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()

        # Skip auth when using the default placeholder key
        if settings.api_secret_key in ("change-me-to-a-random-secret", ""):
            return await call_next(request)

        path = request.url.path

        # Allow public paths
        if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)

        # Check for API key
        api_key = (
            request.headers.get("X-API-Key")
            or _extract_bearer(request.headers.get("Authorization", ""))
        )

        if api_key != settings.api_secret_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key."},
            )

        return await call_next(request)


# ── Request logging ───────────────────────────────────────────


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log request method, path, status, and duration."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        # Skip noisy health checks
        if request.url.path != "/health":
            logger.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            )
        return response


# ── Global error handler ─────────────────────────────────────


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return a clean 500 response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception("http.unhandled_error", path=request.url.path, error=str(exc))
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error."},
            )


# ── Setup helper ──────────────────────────────────────────────


def setup_middleware(app: FastAPI) -> None:
    """Wire all middleware into the FastAPI application.

    Order matters — outermost middleware runs first:
    1. Error handler (catch everything)
    2. Request logging
    3. API key auth
    4. CORS (handled by Starlette's built-in middleware)
    """
    # Add from innermost → outermost (FastAPI reverses the stack)
    add_cors(app)
    app.add_middleware(APIKeyMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(ErrorHandlerMiddleware)


# ── Helpers ───────────────────────────────────────────────────


def _extract_bearer(auth_header: str) -> str:
    """Extract token from ``Bearer <token>`` header."""
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""
