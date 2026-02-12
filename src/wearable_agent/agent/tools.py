"""LangChain tools exposed to the wearable monitoring agent."""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.tools import BaseTool, tool

from wearable_agent.affect.pipeline import AffectPipeline
from wearable_agent.models import MetricType
from wearable_agent.storage.repository import AlertRepository, ReadingRepository

# ── Per-metric reference ranges & interpretation helpers ──────

_METRIC_INFO: dict[str, dict[str, Any]] = {
    "heart_rate": {
        "label": "Heart Rate",
        "unit": "bpm",
        "normal_range": (60, 100),
        "description": "Beats per minute. Resting HR below 60 may indicate bradycardia; above 100 may indicate tachycardia.",
    },
    "resting_heart_rate": {
        "label": "Resting Heart Rate",
        "unit": "bpm",
        "normal_range": (50, 85),
        "description": "Average HR at rest. Lower values generally indicate better cardiovascular fitness.",
    },
    "hrv": {
        "label": "Heart Rate Variability",
        "unit": "ms",
        "normal_range": (20, 120),
        "description": "RMSSD-based HRV in milliseconds. Higher values generally indicate better autonomic balance and recovery.",
    },
    "stress": {
        "label": "Stress Score",
        "unit": "score",
        "normal_range": (1, 50),
        "description": "Fitbit stress management score (1-100). Lower = more physical signs of stress. Above 50 = body showing fewer stress signs.",
    },
    "skin_temperature": {
        "label": "Skin Temperature",
        "unit": "°C",
        "normal_range": (35.0, 38.0),
        "description": "Wrist skin temperature. Deviations from personal baseline may indicate illness or hormonal changes.",
    },
    "breathing_rate": {
        "label": "Breathing Rate",
        "unit": "breaths/min",
        "normal_range": (12, 20),
        "description": "Respirations per minute during sleep. Values outside 12-20 range may warrant attention.",
    },
    "spo2": {
        "label": "Blood Oxygen Saturation",
        "unit": "%",
        "normal_range": (95, 100),
        "description": "SpO2 percentage. Values below 95% may indicate hypoxemia.",
    },
    "sleep": {
        "label": "Sleep Duration",
        "unit": "hours",
        "normal_range": (7, 9),
        "description": "Total sleep time. Adults should aim for 7-9 hours per night.",
    },
    "sleep_efficiency": {
        "label": "Sleep Efficiency",
        "unit": "%",
        "normal_range": (85, 100),
        "description": "Percentage of time in bed actually asleep. Below 85% may indicate poor sleep quality.",
    },
    "steps": {
        "label": "Steps",
        "unit": "steps",
        "normal_range": (5000, 15000),
        "description": "Daily step count. 7,000-10,000 steps/day is a common activity recommendation.",
    },
    "calories": {
        "label": "Calories Burned",
        "unit": "kcal",
        "normal_range": (1500, 3500),
        "description": "Total daily energy expenditure.",
    },
    "distance": {
        "label": "Distance",
        "unit": "km",
        "normal_range": (3.0, 12.0),
        "description": "Total distance covered. Correlated with step count and stride length.",
    },
    "vo2_max": {
        "label": "VO2 Max",
        "unit": "mL/kg/min",
        "normal_range": (30, 60),
        "description": "Cardiorespiratory fitness estimate. Higher is better; varies by age and sex.",
    },
    "floors": {
        "label": "Floors Climbed",
        "unit": "floors",
        "normal_range": (5, 25),
        "description": "Approximate floors climbed (1 floor ≈ 3 m elevation).",
    },
    "body_weight": {
        "label": "Body Weight",
        "unit": "kg",
        "normal_range": (50, 120),
        "description": "Body weight measured from a connected smart scale.",
    },
    "body_fat": {
        "label": "Body Fat",
        "unit": "%",
        "normal_range": (10, 30),
        "description": "Body fat percentage from a connected smart scale or manual entry.",
    },
    "active_zone_minutes": {
        "label": "Active Zone Minutes",
        "unit": "min",
        "normal_range": (15, 120),
        "description": "Minutes spent in fat-burn, cardio, or peak heart rate zones. AHA recommends 150 min/week.",
    },
    "skin_temperature_variation": {
        "label": "Skin Temperature Variation",
        "unit": "°C",
        "normal_range": (-1.0, 1.0),
        "description": "Nightly deviation from personal skin-temperature baseline. Large swings may indicate illness.",
    },
    "sedentary_minutes": {
        "label": "Sedentary Minutes",
        "unit": "min",
        "normal_range": (300, 720),
        "description": "Minutes with little or no activity. Excessive sedentary time is a cardiovascular risk factor.",
    },
    "lightly_active_minutes": {
        "label": "Lightly Active Minutes",
        "unit": "min",
        "normal_range": (60, 300),
        "description": "Minutes in light-intensity activity (walking slowly, light housework).",
    },
    "moderately_active_minutes": {
        "label": "Moderately Active Minutes",
        "unit": "min",
        "normal_range": (15, 90),
        "description": "Minutes in moderate-intensity activity (brisk walking, cycling).",
    },
    "very_active_minutes": {
        "label": "Very Active Minutes",
        "unit": "min",
        "normal_range": (10, 60),
        "description": "Minutes in vigorous-intensity activity (running, HIIT). Key contributor to cardio fitness.",
    },
    "affect_tag": {
        "label": "Affect Self-Report",
        "unit": "tag",
        "normal_range": None,
        "description": "Ecological Momentary Assessment (EMA) self-reported emotional label. Used as ground truth for affect inference.",
    },
}


def _compute_statistics(values: list[float]) -> dict[str, Any]:
    """Compute descriptive statistics for a list of numeric values."""
    if not values:
        return {"count": 0}
    n = len(values)
    mean = statistics.mean(values)
    result: dict[str, Any] = {
        "count": n,
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "mean": round(mean, 3),
        "median": round(statistics.median(values), 3),
    }
    if n >= 2:
        result["stdev"] = round(statistics.stdev(values), 3)
        result["cv_percent"] = round((result["stdev"] / mean) * 100, 1) if mean else 0
    # Quartiles
    if n >= 4:
        sorted_v = sorted(values)
        q1_idx = n // 4
        q3_idx = 3 * n // 4
        result["q1"] = round(sorted_v[q1_idx], 3)
        result["q3"] = round(sorted_v[q3_idx], 3)
        result["iqr"] = round(sorted_v[q3_idx] - sorted_v[q1_idx], 3)
    return result


def _detect_trend(values: list[float], timestamps: list[datetime]) -> dict[str, Any]:
    """Simple linear trend detection from time-ordered values."""
    if len(values) < 3:
        return {"trend": "insufficient_data"}
    # Use index as x-axis for simplicity
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(values)
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    slope = numerator / denominator if denominator else 0
    # Normalise slope relative to mean
    rel_slope = (slope / y_mean * 100) if y_mean else 0
    if abs(rel_slope) < 1:
        direction = "stable"
    elif rel_slope > 0:
        direction = "increasing"
    else:
        direction = "decreasing"
    return {
        "trend": direction,
        "slope_per_sample": round(slope, 4),
        "relative_change_percent": round(rel_slope, 2),
    }


def _flag_anomalies(
    values: list[float], metric_key: str
) -> list[dict[str, Any]]:
    """Flag values outside normal range and statistical outliers (>2 SD)."""
    anomalies: list[dict[str, Any]] = []
    info = _METRIC_INFO.get(metric_key, {})
    normal = info.get("normal_range")
    if len(values) >= 5:
        mean = statistics.mean(values)
        sd = statistics.stdev(values)
        for i, v in enumerate(values):
            reasons = []
            if normal and (v < normal[0] or v > normal[1]):
                reasons.append(f"outside_normal_range ({normal[0]}-{normal[1]})")
            if sd > 0 and abs(v - mean) > 2 * sd:
                reasons.append(f"statistical_outlier (>2σ from mean {mean:.1f})")
            if reasons:
                anomalies.append({"index": i, "value": round(v, 3), "reasons": reasons})
    elif normal:
        for i, v in enumerate(values):
            if v < normal[0] or v > normal[1]:
                anomalies.append({
                    "index": i,
                    "value": round(v, 3),
                    "reasons": [f"outside_normal_range ({normal[0]}-{normal[1]})"],
                })
    return anomalies


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
            metric: Metric name (heart_rate, steps, sleep, spo2, hrv, stress,
                    skin_temperature, breathing_rate, resting_heart_rate,
                    sleep_efficiency, distance, vo2_max, calories, floors).
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
    async def analyse_metric(
        participant_id: str,
        metric: str,
        hours_back: int = 24,
    ) -> dict[str, Any]:
        """Perform a comprehensive analysis of a specific health metric.

        Returns detailed statistics, trend analysis, anomaly detection,
        and reference-range context for the given metric. Use this tool when
        the user asks about a specific metric or wants to understand patterns.

        Args:
            participant_id: Study participant identifier.
            metric: One of: heart_rate, resting_heart_rate, hrv, stress,
                    skin_temperature, breathing_rate, spo2, sleep, sleep_efficiency,
                    steps, calories, distance, vo2_max, floors.
            hours_back: Time window in hours (default 24, max 168 = 7 days).
        """
        try:
            metric_type = MetricType(metric)
        except ValueError:
            return {"error": f"Invalid metric '{metric}'. Valid: {[m.value for m in MetricType]}"}

        end = datetime.now(UTC).replace(tzinfo=None)
        start = end - timedelta(hours=min(hours_back, 168))

        rows = await reading_repo.get_latest(participant_id, metric_type, limit=500)
        if not rows:
            return {
                "metric": metric,
                "count": 0,
                "message": f"No {metric} readings found for participant {participant_id}.",
            }

        # Chronological order
        rows = list(reversed(rows))
        values = [r.value for r in rows]
        timestamps = [r.timestamp for r in rows]

        info = _METRIC_INFO.get(metric, {})
        stats = _compute_statistics(values)
        trend = _detect_trend(values, timestamps)
        anomalies = _flag_anomalies(values, metric)

        return {
            "metric": metric,
            "label": info.get("label", metric),
            "unit": info.get("unit", rows[0].unit if rows else ""),
            "description": info.get("description", ""),
            "normal_range": info.get("normal_range"),
            "time_span": {
                "first_reading": timestamps[0].isoformat(),
                "last_reading": timestamps[-1].isoformat(),
            },
            "statistics": stats,
            "trend": trend,
            "anomalies": anomalies[:20],  # Cap output size
            "anomaly_count": len(anomalies),
            "latest_value": round(values[-1], 3),
            "latest_timestamp": timestamps[-1].isoformat(),
        }

    @tool
    async def compare_metrics(
        participant_id: str,
        metrics: str,
        hours_back: int = 24,
    ) -> dict[str, Any]:
        """Compare multiple health metrics side by side for a participant.

        Useful for spotting correlations (e.g., high stress + low HRV + elevated HR).

        Args:
            participant_id: Study participant identifier.
            metrics: Comma-separated metric names, e.g. "hrv,stress,resting_heart_rate".
            hours_back: Time window in hours (default 24).
        """
        metric_names = [m.strip() for m in metrics.split(",") if m.strip()]
        if not metric_names:
            return {"error": "Provide at least one metric name."}

        results: dict[str, Any] = {}
        for m in metric_names[:6]:  # Cap at 6 metrics
            try:
                mt = MetricType(m)
            except ValueError:
                results[m] = {"error": f"Invalid metric: {m}"}
                continue

            rows = await reading_repo.get_latest(participant_id, mt, limit=200)
            if not rows:
                results[m] = {"count": 0, "message": "No data"}
                continue

            values = [r.value for r in reversed(rows)]
            info = _METRIC_INFO.get(m, {})
            stats = _compute_statistics(values)
            trend = _detect_trend(values, [r.timestamp for r in reversed(rows)])

            results[m] = {
                "label": info.get("label", m),
                "unit": info.get("unit", ""),
                "count": len(values),
                "mean": stats.get("mean"),
                "stdev": stats.get("stdev"),
                "min": stats.get("min"),
                "max": stats.get("max"),
                "latest": round(values[-1], 3) if values else None,
                "trend": trend.get("trend"),
                "normal_range": info.get("normal_range"),
            }

        return {
            "participant_id": participant_id,
            "hours_back": hours_back,
            "metrics": results,
        }

    @tool
    async def list_available_metrics(
        participant_id: str,
    ) -> dict[str, Any]:
        """List all metrics that have data for a participant and show the reading counts.

        Use this when you need to discover which metrics are available before analysis.

        Args:
            participant_id: Study participant identifier.
        """
        metric_summary: dict[str, Any] = {}
        for mt in MetricType:
            rows = await reading_repo.get_latest(participant_id, mt, limit=1)
            if rows:
                r = rows[0]
                metric_summary[mt.value] = {
                    "label": _METRIC_INFO.get(mt.value, {}).get("label", mt.value),
                    "latest_value": r.value,
                    "unit": r.unit or _METRIC_INFO.get(mt.value, {}).get("unit", ""),
                    "latest_timestamp": r.timestamp.isoformat(),
                    "has_data": True,
                }
            # skip metrics with no data to keep output concise

        return {
            "participant_id": participant_id,
            "metrics_with_data": len(metric_summary),
            "metrics": metric_summary,
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

    tools = [
        get_latest_readings,
        get_readings_in_range,
        analyse_metric,
        compare_metrics,
        list_available_metrics,
        get_participant_alerts,
    ]
    if affect_pipeline is not None:
        tools.extend([get_affective_state, get_affect_history])
    return tools
