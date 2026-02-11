"""SQLAlchemy async engine, session factory, and ORM table definitions."""

from __future__ import annotations

from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from wearable_agent.config import get_settings


# ── Base ──────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ── ORM tables ────────────────────────────────────────────────

class SensorReadingRow(Base):
    """Persisted sensor data point."""

    __tablename__ = "sensor_readings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    participant_id: Mapped[str] = mapped_column(String(128), index=True)
    device_type: Mapped[str] = mapped_column(String(32))
    metric_type: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16), default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AlertRow(Base):
    """Persisted alert / notification event."""

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    participant_id: Mapped[str] = mapped_column(String(128), index=True)
    metric_type: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    value: Mapped[float] = mapped_column(Float)
    threshold_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StudyRow(Base):
    """Persisted study configuration."""

    __tablename__ = "studies"

    study_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ParticipantRow(Base):
    """Persisted participant record."""

    __tablename__ = "participants"

    participant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256), default="")
    device_type: Mapped[str] = mapped_column(String(32), default="fitbit")
    active: Mapped[int] = mapped_column(Integer, default=1)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_sync: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OAuthTokenRow(Base):
    """Persisted OAuth 2.0 token for a participant's wearable account."""

    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="fitbit")
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text, default="")
    token_type: Mapped[str] = mapped_column(String(32), default="Bearer")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scopes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── Affect inference tables ───────────────────────────────────


class FeatureWindowRow(Base):
    """Windowed feature aggregation for affect inference."""

    __tablename__ = "feature_windows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    participant_id: Mapped[str] = mapped_column(String(128), index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime)
    window_duration_seconds: Mapped[int] = mapped_column(Integer, default=300)
    activity_context: Mapped[str] = mapped_column(String(32), default="unknown")
    features_json: Mapped[str] = mapped_column(Text, default="{}")
    quality_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class InferenceOutputRow(Base):
    """Persisted affective state inference result."""

    __tablename__ = "inference_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    participant_id: Mapped[str] = mapped_column(String(128), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    feature_window_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    activity_context: Mapped[str] = mapped_column(String(32), default="unknown")

    # Dimensional scores
    arousal_score: Mapped[float] = mapped_column(Float, default=0.5)
    arousal_confidence: Mapped[str] = mapped_column(String(16), default="medium")
    stress_score: Mapped[float] = mapped_column(Float, default=0.5)
    stress_confidence: Mapped[str] = mapped_column(String(16), default="medium")
    valence_score: Mapped[float] = mapped_column(Float, default=0.5)
    valence_confidence: Mapped[str] = mapped_column(String(16), default="low")

    # Discrete emotion
    dominant_emotion: Mapped[str] = mapped_column(String(32), default="unknown")
    dominant_emotion_confidence: Mapped[str] = mapped_column(String(16), default="very_low")

    # Explainability
    contributing_signals_json: Mapped[str] = mapped_column(Text, default="[]")
    explanation: Mapped[str] = mapped_column(Text, default="")
    top_features_json: Mapped[str] = mapped_column(Text, default="{}")

    # Quality & model
    quality_json: Mapped[str] = mapped_column(Text, default="{}")
    model_version: Mapped[str] = mapped_column(String(32), default="rule_v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EMALabelRow(Base):
    """EMA (Ecological Momentary Assessment) self-report ground truth."""

    __tablename__ = "ema_labels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    participant_id: Mapped[str] = mapped_column(String(128), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)

    arousal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    emotion_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    context_note: Mapped[str] = mapped_column(Text, default="")
    trigger: Mapped[str] = mapped_column(String(32), default="scheduled")
    inference_output_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ParticipantBaselineRow(Base):
    """Personalised physiological baselines updated via EWMA."""

    __tablename__ = "participant_baselines"

    participant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # HR baselines by time-of-day
    hr_baseline_morning: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_baseline_afternoon: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_baseline_evening: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_baseline_night: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_baseline_rest: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_std_baseline: Mapped[float | None] = mapped_column(Float, nullable=True)

    # HRV baselines (overnight)
    hrv_rmssd_baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_rmssd_std: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Breathing rate
    br_baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    br_std: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Skin temperature
    skin_temp_baseline: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Sleep
    sleep_duration_baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_efficiency_baseline: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Smoothing
    ewma_alpha: Mapped[float] = mapped_column(Float, default=0.1)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)


# ── Engine & session ──────────────────────────────────────────

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, echo=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency-injectable async session generator (for FastAPI)."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables (idempotent). Use Alembic for migrations in production."""
    # Ensure the parent directory of the SQLite file exists at runtime
    # (covers cases where the dir was cleaned between import and first use).
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite"):
        from pathlib import Path

        # URL format: sqlite+aiosqlite:///path/to/db
        db_path = Path(url.split("///", 1)[-1])
        db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
