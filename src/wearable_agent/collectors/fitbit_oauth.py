"""Shared Fitbit OAuth 2.0 token utilities.

Centralises the token refresh HTTP call so that ``auth.py``,
``scheduler/service.py``, and ``collectors/fitbit.py`` all use a single
implementation.
"""

from __future__ import annotations

import base64

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Fitbit OAuth token endpoint
FITBIT_TOKEN_URL = "https://api.fitbit.com/oauth2/token"


def _make_basic_auth(client_id: str, client_secret: str) -> str:
    """Build an HTTP Basic Authorization header value."""
    return base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()


async def refresh_fitbit_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    *,
    timeout: float = 30,
) -> dict:
    """Exchange a Fitbit refresh token for a new access/refresh token pair.

    Parameters
    ----------
    refresh_token:
        The current refresh token.
    client_id, client_secret:
        Fitbit app credentials for HTTP Basic auth.
    timeout:
        HTTP request timeout in seconds.

    Returns
    -------
    dict
        The raw JSON response from Fitbit, containing at minimum
        ``access_token``, and optionally ``refresh_token``,
        ``expires_in``, and ``scope``.

    Raises
    ------
    httpx.HTTPStatusError
        If Fitbit returns a non-2xx status.
    """
    basic = _make_basic_auth(client_id, client_secret)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            FITBIT_TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        resp.raise_for_status()
        return resp.json()
