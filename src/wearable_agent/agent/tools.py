"""LangChain tools exposed to the wearable monitoring agent."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.tools import BaseTool, tool

from wearable_agent.affect.pipeline import AffectPipeline
from wearable_agent.models import MetricType
from wearable_agent.storage.repository import AlertRepository, ReadingRepository


def create_tools(
    reading_repo: ReadingRepository,
    alert_repo: AlertRepository,
    affect_pipeline: AffectPipeline | None = None,
) -> list[BaseTool]:
    """Create agent tools with bound repository instances.

    This factory pattern avoids global state and makes testing easier by allowing
    repository injection per-agent instance.
    """

    @tool
    async def get_latest_readings(
        participant_id: str,
        metric: str,
        count: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve the most recent sensor readings for a participant.

        Args:
            participant_id: Study participant identifier.
            metric: Metric name (heart_rate, steps, sleep, spo2, hrv).
            count: Number of readings to return (default 10).
        """
        try:
            metric_type = MetricType(metric)
        except ValueError:
            return [{"error": f"Invalid metric: {metric}"}]

        rows = await reading_repo.get_latest(participant_id, metric_type, limit=count)
        return [
            {
                "value": r.value,
                "unit": r.unit,
                "timestamp": r.timestamp.isoformat(),
                "device": r.device_type,
            }
            for r in rows
        ]

    @tool
    async def get_readings_in_range(
        participant_id: str,
        metric: str,
        hours_back: int = 24,
    ) -> dict[str, Any]:
        """Retrieve readings for a participant over a time window and compute summary statistics.

        Args:
            participant_id: Study participant identifier.
            metric: Metric name.
            hours_back: How many hours of history to retrieve.
        """
        try:
            metric_type = MetricType(metric)
        except ValueError:
            return {"error": f"Invalid metric: {metric}"}

        # Use timezone-aware UTC, then convert to naive if DB requires it
        end = datetime.now(UTC).replace(tzinfo=None)
        start = end - timedelta(hours=hours_back)

        rows = await reading_repo.get_range(participant_id, metric_type, start, end)

        if not rows:
            return {"count": 0, "message": "No readings found in the given window."}

        values = [r.value for r in rows]
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": round(sum(values) / len(values), 2),
            "start": rows[0].timestamp.isoformat(),
            "end": rows[-1].timestamp.isoformat(),
        }

    @tool
    async def get_participant_alerts(
        participant_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve recent alerts for a participant.

        Args:
            participant_id: Study participant identifier.
            limit: Max number of alerts to return.
        """
        rows = await alert_repo.get_by_participant(participant_id, limit=limit)
        return [
            {
                "severity": r.severity,
                "metric": r.metric_type,
                "message": r.message,
                "value": r.value,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in rows
        ]

    @tool
    async def get_affective_state(
        participant_id: str,
    ) -> dict[str, Any]:
        """Get the current affective state estimate for a participant.

        Returns arousal, stress, and valence scores with confidence levels,
        contributing physiological signals, and a human-readable explanation.
        Discrete emotion estimates are included but have inherently low accuracy.

        IMPORTANT: Always present these as probabilistic estimates, not diagnoses.
        Note the confidence level and activity context when interpreting results.

        Args:
            participant_id: Study participant identifier.
        """
        if affect_pipeline is None:
            return {"error": "Affect inference pipeline not available."}

        try:
            output = await affect_pipeline.run_inference(participant_id)
            return {
                "arousal_score": output.state.arousal_score,
                "arousal_level": output.state.arousal_level.value,
                "arousal_confidence": output.state.arousal_confidence.value,
                "stress_score": output.state.stress_score,
                "stress_level": output.state.stress_level.value,
                "stress_confidence": output.state.stress_confidence.value,
                "valence_score": output.state.valence_score,
                "valence_level": output.state.valence_level.value,
                "valence_confidence": output.state.valence_confidence.value,
                "dominant_emotion": output.state.dominant_emotion.value,
                "dominant_emotion_confidence": output.state.dominant_emotion_confidence.value,
                "activity_context": output.activity_context.value,
                "contributing_signals": output.contributing_signals,
                "explanation": output.explanation,
                "timestamp": output.timestamp.isoformat(),
            }
        except Exception as exc:
            return {"error": f"Affect inference failed: {exc}"}

    @tool
    async def get_affect_history(
        participant_id: str,
        hours_back: int = 24,
    ) -> dict[str, Any]:
        """Get affect inference history for a participant over a time window.

        Returns a series of arousal/stress/valence scores over time, useful
        for identifying trends in emotional state throughout the day.

        Args:
            participant_id: Study participant identifier.
            hours_back: How many hours of history to retrieve (default 24).
        """
        if affect_pipeline is None:
            return {"error": "Affect inference pipeline not available."}

        end = datetime.now(UTC).replace(tzinfo=None)
        start = end - timedelta(hours=hours_back)

        try:
            history = await affect_pipeline.get_history(participant_id, start, end)
            return {
                "count": len(history),
                "hours_back": hours_back,
                "history": history,
            }
        except Exception as exc:
            return {"error": f"Failed to retrieve affect history: {exc}"}

    tools = [get_latest_readings, get_readings_in_range, get_participant_alerts]
    if affect_pipeline is not None:
        tools.extend([get_affective_state, get_affect_history])
    return tools
