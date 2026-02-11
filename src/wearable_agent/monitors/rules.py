"""Rule engine — evaluates :class:`MonitoringRule` against sensor readings."""

from __future__ import annotations

import structlog

from wearable_agent.models import Alert, AlertSeverity, MetricType, MonitoringRule, SensorReading

logger = structlog.get_logger(__name__)


class RuleEngine:
    """Evaluate a set of declarative monitoring rules against incoming data.

    Rules use a simple expression language evaluated in a restricted
    namespace.  The variable ``value`` is the sensor reading's numeric
    value.

    Example rule condition::

        "value > 120 or value < 50"
    """

    def __init__(self, rules: list[MonitoringRule] | None = None) -> None:
        self._rules: list[MonitoringRule] = rules or []

    # ── Rule management ───────────────────────────────────────

    def add_rule(self, rule: MonitoringRule) -> None:
        self._rules.append(rule)

    def remove_rule(self, rule_id: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.rule_id != rule_id]
        return len(self._rules) < before

    def list_rules(self) -> list[MonitoringRule]:
        return list(self._rules)

    # ── Evaluation ────────────────────────────────────────────

    def evaluate(self, reading: SensorReading) -> list[Alert]:
        """Check all applicable rules and return any fired alerts."""
        alerts: list[Alert] = []
        for rule in self._rules:
            if rule.metric_type != reading.metric_type:
                continue
            if self._condition_met(rule.condition, reading.value):
                alert = Alert(
                    participant_id=reading.participant_id,
                    metric_type=reading.metric_type,
                    severity=rule.severity,
                    message=rule.message_template.format(
                        metric_type=reading.metric_type.value,
                        value=reading.value,
                    ),
                    value=reading.value,
                )
                alerts.append(alert)
                logger.info(
                    "rule_engine.alert_fired",
                    rule_id=rule.rule_id,
                    participant=reading.participant_id,
                    value=reading.value,
                    severity=rule.severity.value,
                )
        return alerts

    def evaluate_batch(self, readings: list[SensorReading]) -> list[Alert]:
        """Evaluate many readings and collect all alerts."""
        alerts: list[Alert] = []
        for reading in readings:
            alerts.extend(self.evaluate(reading))
        return alerts

    # ── Internals ─────────────────────────────────────────────

    @staticmethod
    def _condition_met(condition: str, value: float) -> bool:
        """Safely evaluate a rule condition string.

        Only ``value`` is exposed; builtins are blocked.
        """
        try:
            return bool(eval(condition, {"__builtins__": {}}, {"value": value}))
        except Exception as exc:
            logger.error("rule_engine.condition_eval_error", condition=condition, error=str(exc))
            return False
