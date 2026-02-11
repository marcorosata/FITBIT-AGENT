"""Centralised application settings loaded from environment / .env file."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _is_railway() -> bool:
    """Detect Railway deployment via any of its well-known env vars."""
    return any(
        os.getenv(v)
        for v in ("RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID")
    )


def _resolve_db_dir() -> Path:
    """Return (and create) the directory that holds the SQLite file."""
    if _is_railway():
        d = Path("/tmp/data")
    else:
        d = _PROJECT_ROOT / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


_DB_DIR = _resolve_db_dir()
_DEFAULT_DB_URL = f"sqlite+aiosqlite:///{_DB_DIR / 'wearable_agent.db'}"


class Settings(BaseSettings):
    """All runtime configuration for the wearable-agent framework.

    Values are read from environment variables first, then from a *.env* file
    located at the project root.  Nested prefixes are **not** used: every
    variable lives in the flat ``WEARABLE_AGENT_`` namespace (stripped
    automatically by *pydantic-settings*).
    """

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM ───────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # ── Fitbit OAuth 2 ────────────────────────────────────────
    fitbit_client_id: str = ""
    fitbit_client_secret: str = ""
    fitbit_redirect_uri: str = "http://localhost:8000/auth/fitbit/callback"
    fitbit_access_token: str = ""
    fitbit_refresh_token: str = ""

    # ── Fitbit API behaviour ──────────────────────────────────
    fitbit_rate_limit_per_hour: int = 150  # Fitbit default per-user limit
    fitbit_request_timeout: float = 30.0
    fitbit_api_base_url: str = "https://api.fitbit.com"

    # ── Database ──────────────────────────────────────────────
    database_url: str = _DEFAULT_DB_URL

    # ── API server ────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = int(os.getenv("PORT", "8000"))  # Railway sets PORT env var
    api_secret_key: str = "change-me-to-a-random-secret"

    # ── Notifications ─────────────────────────────────────────
    webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notification_email_from: str = ""

    # ── CORS ──────────────────────────────────────────────────
    cors_origins: str = "*"  # comma-separated origins, or "*" for all

    # ── Scheduler ─────────────────────────────────────────────
    scheduler_enabled: bool = True
    scheduler_collect_interval_minutes: int = 5
    scheduler_max_concurrent_syncs: int = 3

    # ── Agent behaviour ───────────────────────────────────────
    agent_check_interval_seconds: int = 300
    agent_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── Affect inference ──────────────────────────────────────
    affect_window_seconds: int = 300  # Feature window duration
    affect_ewma_alpha: float = 0.1  # EWMA smoothing factor for baselines
    affect_min_baseline_days: int = 7  # Min days before personalised baseline is trusted
    affect_stress_ema_threshold: float = 0.65  # Stress score triggering EMA prompt
    affect_max_daily_ema: int = 8  # Max EMA prompts per day
    affect_sync_lag_threshold_seconds: int = 1800  # Stale data if sync > 30 min


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` singleton."""
    return Settings()  # pydantic-settings handles env reading each time
