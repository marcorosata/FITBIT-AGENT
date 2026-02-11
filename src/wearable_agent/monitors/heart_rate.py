"""Heart-rate–specific monitoring helpers and default rules."""

from __future__ import annotations

from wearable_agent.models import AlertSeverity, MetricType, MonitoringRule
from wearable_agent.monitors.rules import RuleEngine


def default_heart_rate_rules() -> list[MonitoringRule]:
    """Return sensible default rules for resting heart-rate monitoring.

    These thresholds are intentionally conservative and should be
    adjusted per study protocol.
    """
    return [
        MonitoringRule(
            rule_id="hr_high_warning",
            metric_type=MetricType.HEART_RATE,
            condition="value > 100",
            severity=AlertSeverity.WARNING,
            message_template=(
                "Elevated heart rate detected: {value} bpm exceeds 100 bpm threshold."
            ),
        ),
        MonitoringRule(
            rule_id="hr_high_critical",
            metric_type=MetricType.HEART_RATE,
            condition="value > 150",
            severity=AlertSeverity.CRITICAL,
            message_template=(
                "CRITICAL: Heart rate {value} bpm exceeds 150 bpm — immediate review recommended."
            ),
        ),
        MonitoringRule(
            rule_id="hr_low_warning",
            metric_type=MetricType.HEART_RATE,
            condition="value < 45",
            severity=AlertSeverity.WARNING,
            message_template=(
                "Unusually low heart rate detected: {value} bpm is below 45 bpm threshold."
            ),
        ),
    ]


def default_spo2_rules() -> list[MonitoringRule]:
    """Return default rules for blood-oxygen saturation (SpO₂) monitoring."""
    return [
        MonitoringRule(
            rule_id="spo2_low_warning",
            metric_type=MetricType.SPO2,
            condition="value < 95",
            severity=AlertSeverity.WARNING,
            message_template=(
                "Low SpO₂ detected: {value}% is below the 95% threshold."
            ),
        ),
        MonitoringRule(
            rule_id="spo2_low_critical",
            metric_type=MetricType.SPO2,
            condition="value < 90",
            severity=AlertSeverity.CRITICAL,
            message_template=(
                "CRITICAL: SpO₂ {value}% is dangerously low — immediate review recommended."
            ),
        ),
    ]


def default_hrv_rules() -> list[MonitoringRule]:
    """Return default rules for Heart Rate Variability (HRV RMSSD) monitoring.

    Very low HRV can indicate stress, overtraining, or autonomic dysfunction.
    """
    return [
        MonitoringRule(
            rule_id="hrv_low_warning",
            metric_type=MetricType.HRV,
            condition="value < 20",
            severity=AlertSeverity.WARNING,
            message_template=(
                "Low HRV detected: RMSSD {value} ms is below 20 ms threshold."
            ),
        ),
    ]


def default_skin_temperature_rules() -> list[MonitoringRule]:
    """Return default rules for nightly skin-temperature deviation monitoring.

    Fitbit reports skin temperature as a deviation from baseline (°C).
    """
    return [
        MonitoringRule(
            rule_id="temp_high_warning",
            metric_type=MetricType.SKIN_TEMPERATURE,
            condition="value > 1.5",
            severity=AlertSeverity.WARNING,
            message_template=(
                "Elevated skin temperature deviation: {value}°C above baseline."
            ),
        ),
        MonitoringRule(
            rule_id="temp_low_warning",
            metric_type=MetricType.SKIN_TEMPERATURE,
            condition="value < -1.5",
            severity=AlertSeverity.WARNING,
            message_template=(
                "Low skin temperature deviation: {value}°C below baseline."
            ),
        ),
    ]


def default_breathing_rate_rules() -> list[MonitoringRule]:
    """Return default rules for breathing rate (breaths per minute)."""
    return [
        MonitoringRule(
            rule_id="br_high_warning",
            metric_type=MetricType.BREATHING_RATE,
            condition="value > 25",
            severity=AlertSeverity.WARNING,
            message_template=(
                "High breathing rate detected: {value} brpm exceeds 25 brpm."
            ),
        ),
        MonitoringRule(
            rule_id="br_low_warning",
            metric_type=MetricType.BREATHING_RATE,
            condition="value < 10",
            severity=AlertSeverity.WARNING,
            message_template=(
                "Low breathing rate detected: {value} brpm is below 10 brpm."
            ),
        ),
    ]


def all_default_rules() -> list[MonitoringRule]:
    """Return all default monitoring rules across every supported metric."""
    return [
        *default_heart_rate_rules(),
        *default_spo2_rules(),
        *default_hrv_rules(),
        *default_skin_temperature_rules(),
        *default_breathing_rate_rules(),
    ]


def create_heart_rate_engine() -> RuleEngine:
    """Convenience factory for a pre-configured heart-rate rule engine."""
    return RuleEngine(rules=default_heart_rate_rules())


def create_full_engine() -> RuleEngine:
    """Factory for a rule engine pre-loaded with all default rules."""
    return RuleEngine(rules=all_default_rules())
