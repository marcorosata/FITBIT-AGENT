"""Request / response models shared across API route modules."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from wearable_agent.models import AlertSeverity, DeviceType, MetricType


class IngestRequest(BaseModel):
    participant_id: str
    device_type: DeviceType
    metric_type: MetricType
    value: float
    unit: str = ""
    timestamp: datetime | None = None
    metadata: dict[str, Any] = {}


class AnalyseRequest(BaseModel):
    query: str


class RuleRequest(BaseModel):
    metric_type: MetricType
    condition: str
    severity: AlertSeverity = AlertSeverity.WARNING
    message_template: str = "Metric {metric_type} value {value} breached rule."


class AffectRequest(BaseModel):
    """Trigger affect inference for a participant."""
    window_seconds: int = 300


class EMARequest(BaseModel):
    """Submit an EMA self-report label."""
    participant_id: str
    arousal: int | None = None       # 1-9 SAM
    valence: int | None = None       # 1-9 SAM
    stress: int | None = None        # 1-5
    emotion_tag: str | None = None   # DiscreteEmotion value
    context_note: str = ""
    trigger: str = "user_initiated"
    inference_output_id: str | None = None
