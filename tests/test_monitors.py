"""Tests for the monitoring rules engine."""

from wearable_agent.models import AlertSeverity, MetricType, MonitoringRule, SensorReading
from wearable_agent.monitors.rules import RuleEngine


class TestRuleEngine:
    """Unit tests for :class:`RuleEngine`."""

    def test_no_alert_for_normal_reading(self, rule_engine, sample_reading):
        alerts = rule_engine.evaluate(sample_reading)
        assert alerts == []

    def test_warning_for_high_hr(self, rule_engine, high_hr_reading):
        alerts = rule_engine.evaluate(high_hr_reading)
        severities = {a.severity for a in alerts}
        assert AlertSeverity.WARNING in severities
        assert AlertSeverity.CRITICAL in severities  # 160 > 150

    def test_warning_for_low_hr(self, rule_engine, low_hr_reading):
        alerts = rule_engine.evaluate(low_hr_reading)
        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.WARNING

    def test_add_and_remove_rule(self, rule_engine):
        new_rule = MonitoringRule(
            rule_id="test_rule",
            metric_type=MetricType.STEPS,
            condition="value < 100",
            severity=AlertSeverity.INFO,
            message_template="Low steps: {value}.",
        )
        rule_engine.add_rule(new_rule)
        assert len(rule_engine.list_rules()) == 4

        removed = rule_engine.remove_rule("test_rule")
        assert removed is True
        assert len(rule_engine.list_rules()) == 3

    def test_batch_evaluation(self, rule_engine, sample_reading, high_hr_reading):
        alerts = rule_engine.evaluate_batch([sample_reading, high_hr_reading])
        assert len(alerts) >= 1  # at least for the high reading

    def test_invalid_condition_does_not_crash(self):
        engine = RuleEngine(rules=[
            MonitoringRule(
                rule_id="bad",
                metric_type=MetricType.HEART_RATE,
                condition="invalid python!",
                severity=AlertSeverity.WARNING,
                message_template="Should not fire.",
            ),
        ])
        reading = SensorReading(
            participant_id="P001",
            device_type="fitbit",
            metric_type=MetricType.HEART_RATE,
            value=80.0,
            unit="bpm",
        )
        alerts = engine.evaluate(reading)
        assert alerts == []
