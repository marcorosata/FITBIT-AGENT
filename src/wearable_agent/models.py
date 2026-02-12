"""Shared Pydantic models used across the framework."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ── Enums ─────────────────────────────────────────────────────

class DeviceType(str, Enum):
    """Supported wearable device families."""
    FITBIT = "fitbit"
    LIFESNAPS = "lifesnaps"
    APPLE_WATCH = "apple_watch"
    GARMIN = "garmin"
    GENERIC = "generic"


class MetricType(str, Enum):
    """Categories of physiological / behavioural metrics.

    Covers all resource categories available via the Fitbit Web API.
    """

    HEART_RATE = "heart_rate"
    STEPS = "steps"
    SLEEP = "sleep"
    SPO2 = "spo2"
    SKIN_TEMPERATURE = "skin_temperature"
    HRV = "hrv"
    CALORIES = "calories"
    DISTANCE = "distance"
    FLOORS = "floors"
    BREATHING_RATE = "breathing_rate"
    BODY_WEIGHT = "body_weight"
    BODY_FAT = "body_fat"
    VO2_MAX = "vo2_max"
    ACTIVE_ZONE_MINUTES = "active_zone_minutes"
    STRESS = "stress"
    SLEEP_EFFICIENCY = "sleep_efficiency"
    RESTING_HEART_RATE = "resting_heart_rate"
    SKIN_TEMPERATURE_VARIATION = "skin_temperature_variation"
    SEDENTARY_MINUTES = "sedentary_minutes"
    LIGHTLY_ACTIVE_MINUTES = "lightly_active_minutes"
    MODERATELY_ACTIVE_MINUTES = "moderately_active_minutes"
    VERY_ACTIVE_MINUTES = "very_active_minutes"
    AFFECT_TAG = "affect_tag"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# ── Data transfer objects ─────────────────────────────────────

class SensorReading(BaseModel):
    """A single sensor data point collected from a wearable device."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    participant_id: str
    device_type: DeviceType
    metric_type: MetricType
    value: float
    unit: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Alert(BaseModel):
    """An alert generated when a monitored value breaches a rule."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    participant_id: str
    metric_type: MetricType
    severity: AlertSeverity
    message: str
    value: float
    threshold_low: float | None = None
    threshold_high: float | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StudyConfig(BaseModel):
    """Configuration for a research study / data-collection campaign."""
    study_id: str
    name: str
    description: str = ""
    metrics: list[MetricType]
    collection_interval_seconds: int = 300
    participants: list[str] = Field(default_factory=list)
    rules: list[MonitoringRule] = Field(default_factory=list)


class MonitoringRule(BaseModel):
    """A declarative rule that the agent evaluates against incoming data."""
    rule_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    metric_type: MetricType
    condition: str  # e.g. "value > 100 or value < 50"
    severity: AlertSeverity = AlertSeverity.WARNING
    message_template: str = "Metric {metric_type} value {value} breached rule."


class Participant(BaseModel):
    """A study participant with device configuration."""
    participant_id: str
    display_name: str = ""
    device_type: DeviceType = DeviceType.FITBIT
    active: bool = True
    enrolled_at: datetime = Field(default_factory=datetime.utcnow)
    last_sync: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OAuthToken(BaseModel):
    """OAuth 2.0 token pair for a participant's device account."""
    participant_id: str
    provider: str = "fitbit"
    access_token: str
    refresh_token: str = ""
    token_type: str = "Bearer"
    expires_at: datetime | None = None
    scopes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# Resolve forward reference
StudyConfig.model_rebuild()
