"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from wearable_agent.models import (
    AlertSeverity,
    DeviceType,
    MetricType,
    MonitoringRule,
    SensorReading,
)
from wearable_agent.monitors.rules import RuleEngine
from wearable_agent.notifications.handlers import NotificationDispatcher


@pytest.fixture
def sample_reading() -> SensorReading:
    return SensorReading(
        participant_id="P001",
        device_type=DeviceType.FITBIT,
        metric_type=MetricType.HEART_RATE,
        value=75.0,
        unit="bpm",
    )


@pytest.fixture
def high_hr_reading() -> SensorReading:
    return SensorReading(
        participant_id="P001",
        device_type=DeviceType.FITBIT,
        metric_type=MetricType.HEART_RATE,
        value=160.0,
        unit="bpm",
    )


@pytest.fixture
def low_hr_reading() -> SensorReading:
    return SensorReading(
        participant_id="P001",
        device_type=DeviceType.FITBIT,
        metric_type=MetricType.HEART_RATE,
        value=38.0,
        unit="bpm",
    )


@pytest.fixture
def hr_rules() -> list[MonitoringRule]:
    return [
        MonitoringRule(
            rule_id="hr_high",
            metric_type=MetricType.HEART_RATE,
            condition="value > 100",
            severity=AlertSeverity.WARNING,
            message_template="HR {value} bpm > 100.",
        ),
        MonitoringRule(
            rule_id="hr_critical",
            metric_type=MetricType.HEART_RATE,
            condition="value > 150",
            severity=AlertSeverity.CRITICAL,
            message_template="HR {value} bpm > 150!",
        ),
        MonitoringRule(
            rule_id="hr_low",
            metric_type=MetricType.HEART_RATE,
            condition="value < 45",
            severity=AlertSeverity.WARNING,
            message_template="HR {value} bpm < 45.",
        ),
    ]


@pytest.fixture
def rule_engine(hr_rules: list[MonitoringRule]) -> RuleEngine:
    return RuleEngine(rules=hr_rules)


@pytest.fixture
def dispatcher() -> NotificationDispatcher:
    return NotificationDispatcher()
