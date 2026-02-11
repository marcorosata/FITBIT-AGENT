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


# Resolve forward reference
StudyConfig.model_rebuild()
