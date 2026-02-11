"""Fitbit OAuth 2.0 Authorization Code Grant flow.

Endpoints
~~~~~~~~~
* ``GET /auth/fitbit?participant_id=...`` — redirect user to Fitbit login
* ``GET /auth/fitbit/callback`` — handle Fitbit redirect with auth code
* ``POST /auth/fitbit/refresh/{participant_id}`` — manually refresh tokens
* ``DELETE /auth/fitbit/{participant_id}`` — revoke & delete stored tokens

The flow stores access and refresh tokens per-participant in the database
so the scheduler can collect data on their behalf.
"""

from __future__ import annotations

import base64
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from wearable_agent.config import get_settings
from wearable_agent.storage.repository import ParticipantRepository, TokenRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth/fitbit", tags=["auth"])

# In-memory CSRF state store (use Redis in production at scale)
_pending_states: dict[str, str] = {}  # state → participant_id

# Fitbit OAuth endpoints
_FITBIT_AUTH_URL = "https://www.fitbit.com/oauth2/authorize"
_FITBIT_TOKEN_URL = "https://api.fitbit.com/oauth2/token"
_FITBIT_REVOKE_URL = "https://api.fitbit.com/oauth2/revoke"

# Scopes we request
_SCOPES = (
    "activity heartrate sleep profile settings weight temperature "
    "respiratory_rate oxygen_saturation"
)


# ── Step 1: Redirect to Fitbit ────────────────────────────────


@router.get("", summary="Start Fitbit OAuth flow")
async def fitbit_authorize(
    participant_id: str = Query(..., description="Participant ID to link"),
):
    """Redirect the user to Fitbit's OAuth consent page.

    The ``participant_id`` is stored against a CSRF state token so the
    callback can associate the resulting tokens with the right participant.
    """
    settings = get_settings()
    if not settings.fitbit_client_id:
        raise HTTPException(500, "FITBIT_CLIENT_ID not configured.")

    state = secrets.token_urlsafe(32)
    _pending_states[state] = participant_id

    params = {
        "response_type": "code",
        "client_id": settings.fitbit_client_id,
        "redirect_uri": settings.fitbit_redirect_uri,
        "scope": _SCOPES,
        "state": state,
        "prompt": "login consent",
    }
    url = f"{_FITBIT_AUTH_URL}?{urlencode(params)}"
    logger.info("oauth.redirect", participant=participant_id)
    return RedirectResponse(url)


# ── Step 2: Handle callback ──────────────────────────────────


@router.get("/callback", summary="Fitbit OAuth callback")
async def fitbit_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    error_description: str = Query(None),
):
    """Exchange the authorisation code for access + refresh tokens."""
    if error:
        logger.warning("oauth.error", error=error, desc=error_description)
        return HTMLResponse(
            f"<h2>Fitbit authorisation failed</h2><p>{error}: {error_description}</p>",
            status_code=400,
        )

    if not state or state not in _pending_states:
        raise HTTPException(400, "Invalid or expired state parameter.")

    participant_id = _pending_states.pop(state)

    if not code:
        raise HTTPException(400, "Missing authorisation code.")

    settings = get_settings()
    basic = base64.b64encode(
        f"{settings.fitbit_client_id}:{settings.fitbit_client_secret}".encode()
    ).decode()

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _FITBIT_TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.fitbit_redirect_uri,
            },
        )

    if resp.status_code != 200:
        logger.error("oauth.token_exchange_failed", status=resp.status_code, body=resp.text)
        raise HTTPException(502, "Failed to exchange authorisation code with Fitbit.")

    body = resp.json()
    access_token = body["access_token"]
    refresh_token = body.get("refresh_token", "")
    expires_in = body.get("expires_in", 28800)  # default 8 hours
    scopes = body.get("scope", "")

    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # Persist tokens
    token_repo = TokenRepository()
    await token_repo.upsert(
        participant_id=participant_id,
        access_token=access_token,
        refresh_token=refresh_token,
        provider="fitbit",
        expires_at=expires_at,
        scopes=scopes,
    )

    # Ensure participant exists
    participant_repo = ParticipantRepository()
    existing = await participant_repo.get(participant_id)
    if existing is None:
        await participant_repo.save(participant_id=participant_id, device_type="fitbit")

    logger.info("oauth.tokens_saved", participant=participant_id, scopes=scopes)

    return HTMLResponse(
        f"<h2>Success!</h2>"
        f"<p>Fitbit account linked for participant <b>{participant_id}</b>.</p>"
        f"<p>You can close this window.</p>"
    )


# ── Token refresh ─────────────────────────────────────────────


@router.post("/refresh/{participant_id}", summary="Refresh Fitbit tokens")
async def refresh_tokens(participant_id: str):
    """Manually trigger a token refresh for a participant."""
    token_repo = TokenRepository()
    token_row = await token_repo.get(participant_id, "fitbit")
    if token_row is None:
        raise HTTPException(404, "No tokens found for this participant.")

    if not token_row.refresh_token:
        raise HTTPException(400, "No refresh token available.")

    settings = get_settings()
    basic = base64.b64encode(
        f"{settings.fitbit_client_id}:{settings.fitbit_client_secret}".encode()
    ).decode()

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _FITBIT_TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_row.refresh_token,
            },
        )

    if resp.status_code != 200:
        logger.error("oauth.refresh_failed", participant=participant_id, status=resp.status_code)
        raise HTTPException(502, "Token refresh failed.")

    body = resp.json()
    expires_at = datetime.utcnow() + timedelta(seconds=body.get("expires_in", 28800))

    await token_repo.upsert(
        participant_id=participant_id,
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token", token_row.refresh_token),
        provider="fitbit",
        expires_at=expires_at,
        scopes=body.get("scope", token_row.scopes),
    )

    logger.info("oauth.tokens_refreshed", participant=participant_id)
    return {"status": "refreshed", "expires_at": expires_at.isoformat()}


# ── Token status & revocation ─────────────────────────────────


@router.get("/status/{participant_id}", summary="Check token status")
async def token_status(participant_id: str):
    """Check whether valid tokens exist for a participant."""
    token_repo = TokenRepository()
    token_row = await token_repo.get(participant_id, "fitbit")
    if token_row is None:
        return {"linked": False}

    expired = (
        token_row.expires_at is not None
        and token_row.expires_at < datetime.utcnow()
    )
    return {
        "linked": True,
        "expired": expired,
        "expires_at": token_row.expires_at.isoformat() if token_row.expires_at else None,
        "scopes": token_row.scopes,
        "has_refresh_token": bool(token_row.refresh_token),
    }


@router.delete("/{participant_id}", summary="Revoke & delete tokens")
async def revoke_tokens(participant_id: str):
    """Revoke the Fitbit access token and delete stored tokens."""
    token_repo = TokenRepository()
    token_row = await token_repo.get(participant_id, "fitbit")
    if token_row is None:
        raise HTTPException(404, "No tokens found for this participant.")

    # Attempt to revoke at Fitbit (best-effort)
    settings = get_settings()
    basic = base64.b64encode(
        f"{settings.fitbit_client_id}:{settings.fitbit_client_secret}".encode()
    ).decode()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                _FITBIT_REVOKE_URL,
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"token": token_row.access_token},
            )
    except Exception:
        logger.warning("oauth.revoke_failed", participant=participant_id)

    await token_repo.delete(participant_id, "fitbit")
    logger.info("oauth.tokens_revoked", participant=participant_id)
    return {"status": "revoked"}
