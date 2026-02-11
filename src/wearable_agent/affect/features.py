"""Feature engineering — windowed aggregation, baseline, quality gating.

This module transforms raw :class:`SensorReading` time-series into
:class:`FeatureWindow` objects suitable for the affect inference engine.

Key responsibilities
--------------------
1. **Activity-context classification** — classify each window as rest,
   low/moderate/high movement or sleep, using steps + METs + AZM + time.
2. **Windowed aggregation** — compute HR mean/std/slope, counts, etc.
   over configurable time windows (default 5 min).
3. **Personalised baseline** — maintain EWMA baselines by time-of-day
   and compute z-score deviations.
4. **Quality gating** — attach data-quality flags (sync lag, wear,
   coverage) so the inference engine can degrade gracefully.
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timedelta
from typing import Sequence

import structlog

from wearable_agent.affect.models import (
    ActivityContext,
    FeatureWindow,
    ParticipantBaseline,
    QualityFlags,
)
from wearable_agent.models import MetricType
from wearable_agent.storage.database import SensorReadingRow

logger = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────

# Activity context thresholds (per 5-minute window defaults)
_STEPS_REST_THRESHOLD = 5  # ≤5 steps → rest
_STEPS_LOW_THRESHOLD = 50
_STEPS_MODERATE_THRESHOLD = 200
_METS_REST_THRESHOLD = 1.5

# Minimum data-point count for reliable features
_MIN_HR_POINTS = 3

# Time-of-day bands
_TOD_BANDS = {
    "morning": (6, 12),
    "afternoon": (12, 18),
    "evening": (18, 24),
    "night": (0, 6),
}


# ── Activity context classifier ──────────────────────────────


def classify_activity_context(
    steps: float | None,
    mets_mean: float | None,
    azm_minutes: float | None,
    hour: int,
    sleep_period: bool = False,
) -> ActivityContext:
    """Classify the physiological context of a time window.

    Parameters
    ----------
    steps : float | None
        Total steps in the window.
    mets_mean : float | None
        Mean MET value in the window (if available).
    azm_minutes : float | None
        Active Zone Minutes in the window.
    hour : int
        Hour of day (0-23) for circadian heuristic.
    sleep_period : bool
        True if the window overlaps a known sleep period.

    Returns
    -------
    ActivityContext
        Classification of physical activity context.
    """
    if sleep_period:
        return ActivityContext.SLEEP

    effective_steps = steps if steps is not None else 0

    # Use METs if available for more reliable classification
    if mets_mean is not None:
        if mets_mean <= _METS_REST_THRESHOLD and effective_steps <= _STEPS_REST_THRESHOLD:
            return ActivityContext.REST
        if mets_mean <= 3.0:
            return ActivityContext.LOW_MOVEMENT
        if mets_mean <= 6.0:
            return ActivityContext.MODERATE_MOVEMENT
        return ActivityContext.HIGH_MOVEMENT

    # Fallback to steps-only
    if effective_steps <= _STEPS_REST_THRESHOLD:
        return ActivityContext.REST
    if effective_steps <= _STEPS_LOW_THRESHOLD:
        return ActivityContext.LOW_MOVEMENT
    if effective_steps <= _STEPS_MODERATE_THRESHOLD:
        return ActivityContext.MODERATE_MOVEMENT
    return ActivityContext.HIGH_MOVEMENT


# ── Time-of-day helpers ──────────────────────────────────────


def get_time_of_day_band(hour: int) -> str:
    """Return time-of-day band label for circadian baseline segmentation."""
    for band, (start, end) in _TOD_BANDS.items():
        if start <= hour < end:
            return band
    return "night"  # fallback for hour=24


def _linear_slope(values: Sequence[float]) -> float:
    """Compute the linear slope of a sequence (least-squares)."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(values)
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator


# ── Feature extraction from readings ─────────────────────────


def extract_feature_window(
    participant_id: str,
    readings: Sequence[SensorReadingRow],
    window_start: datetime,
    window_end: datetime,
    baseline: ParticipantBaseline | None = None,
    sleep_readings: Sequence[SensorReadingRow] | None = None,
    overnight_readings: dict[MetricType, Sequence[SensorReadingRow]] | None = None,
    last_sync_time: datetime | None = None,
) -> FeatureWindow:
    """Build a :class:`FeatureWindow` from raw readings within a time range.

    Parameters
    ----------
    readings
        All ``SensorReadingRow`` objects within [window_start, window_end],
        across multiple metric types.
    baseline
        Personalised baseline for z-score computation.  ``None`` for first-run.
    sleep_readings
        Most recent sleep log readings (used for overnight features).
    overnight_readings
        Dict mapping MetricType → readings for overnight metrics
        (HRV, BR, SpO2, skin temp).
    last_sync_time
        Last device sync timestamp for quality gating.
    """
    overnight_readings = overnight_readings or {}
    sleep_readings = sleep_readings or []

    # ── Partition readings by metric type
    by_metric: dict[str, list[SensorReadingRow]] = {}
    for r in readings:
        by_metric.setdefault(r.metric_type, []).append(r)

    # ── HR features
    hr_readings = by_metric.get(MetricType.HEART_RATE.value, [])
    hr_values = [r.value for r in hr_readings]
    hr_mean = statistics.mean(hr_values) if hr_values else None
    hr_std = statistics.stdev(hr_values) if len(hr_values) >= 2 else None
    hr_min = min(hr_values) if hr_values else None
    hr_max = max(hr_values) if hr_values else None
    hr_slope = _linear_slope(hr_values) if len(hr_values) >= 2 else None

    # Resting HR from metadata
    resting_hr: float | None = None
    for r in hr_readings:
        meta = json.loads(r.metadata_json) if r.metadata_json else {}
        if meta.get("type") == "resting":
            resting_hr = r.value
            break

    # ── Steps/calories/METs
    step_readings = by_metric.get(MetricType.STEPS.value, [])
    steps_in_window = sum(r.value for r in step_readings) if step_readings else None

    cal_readings = by_metric.get(MetricType.CALORIES.value, [])
    calories_in_window = sum(r.value for r in cal_readings) if cal_readings else None

    # METs from calories metadata if available
    mets_values: list[float] = []
    for r in cal_readings:
        meta = json.loads(r.metadata_json) if r.metadata_json else {}
        if "mets" in meta:
            mets_values.append(float(meta["mets"]))
    mets_mean = statistics.mean(mets_values) if mets_values else None

    # AZM
    azm_readings = by_metric.get(MetricType.ACTIVE_ZONE_MINUTES.value, [])
    azm_minutes = sum(r.value for r in azm_readings) if azm_readings else None

    # ── Activity context
    mid_hour = window_start.hour
    is_sleep = any(
        r.metric_type == MetricType.SLEEP.value for r in readings
    )
    activity_ctx = classify_activity_context(
        steps=steps_in_window,
        mets_mean=mets_mean,
        azm_minutes=azm_minutes,
        hour=mid_hour,
        sleep_period=is_sleep,
    )

    # ── Baseline deviations
    hr_baseline_dev: float | None = None
    if baseline and hr_mean is not None:
        band = get_time_of_day_band(mid_hour)
        ref = getattr(baseline, f"hr_baseline_{band}", None)
        std = baseline.hr_std_baseline
        if ref is not None and std and std > 0:
            hr_baseline_dev = (hr_mean - ref) / std

    # ── Overnight features (HRV, BR, SpO2, skin temp)
    hrv_readings = overnight_readings.get(MetricType.HRV, [])
    hrv_rmssd: float | None = None
    hrv_deep_rmssd: float | None = None
    hrv_rmssd_dev: float | None = None
    if hrv_readings:
        hrv_rmssd = hrv_readings[0].value
        meta = json.loads(hrv_readings[0].metadata_json) if hrv_readings[0].metadata_json else {}
        hrv_deep_rmssd = meta.get("deep_rmssd")
        if isinstance(hrv_deep_rmssd, (int, float)):
            hrv_deep_rmssd = float(hrv_deep_rmssd)
        else:
            hrv_deep_rmssd = None
        if baseline and baseline.hrv_rmssd_baseline and baseline.hrv_rmssd_std:
            if baseline.hrv_rmssd_std > 0:
                hrv_rmssd_dev = (hrv_rmssd - baseline.hrv_rmssd_baseline) / baseline.hrv_rmssd_std

    br_readings = overnight_readings.get(MetricType.BREATHING_RATE, [])
    breathing_rate: float | None = None
    br_dev: float | None = None
    if br_readings:
        breathing_rate = br_readings[0].value
        if baseline and baseline.br_baseline and baseline.br_std:
            if baseline.br_std > 0:
                br_dev = (breathing_rate - baseline.br_baseline) / baseline.br_std

    spo2_readings = overnight_readings.get(MetricType.SPO2, [])
    spo2_avg: float | None = None
    spo2_min: float | None = None
    if spo2_readings:
        spo2_avg = spo2_readings[0].value
        meta = json.loads(spo2_readings[0].metadata_json) if spo2_readings[0].metadata_json else {}
        spo2_min_raw = meta.get("min")
        spo2_min = float(spo2_min_raw) if spo2_min_raw is not None else None

    temp_readings = overnight_readings.get(MetricType.SKIN_TEMPERATURE, [])
    skin_temp_dev: float | None = None
    if temp_readings:
        skin_temp_dev = temp_readings[0].value  # already nightlyRelative

    # ── Sleep features
    sleep_dur: float | None = None
    sleep_eff: float | None = None
    sleep_deep_pct: float | None = None
    sleep_rem_pct: float | None = None
    sleep_wake_pct: float | None = None
    sleep_wake_count: int | None = None
    sleep_info_code: int | None = None

    if sleep_readings:
        main_sleep = sleep_readings[0]  # most recent
        sleep_dur = main_sleep.value  # minutesAsleep
        meta = json.loads(main_sleep.metadata_json) if main_sleep.metadata_json else {}
        sleep_eff = meta.get("efficiency")
        if isinstance(sleep_eff, (int, float)):
            sleep_eff = float(sleep_eff)
        else:
            sleep_eff = None

        total = sleep_dur or 1
        deep = meta.get("deep_minutes")
        light = meta.get("light_minutes")
        rem = meta.get("rem_minutes")
        wake = meta.get("wake_minutes")

        if deep is not None:
            sleep_deep_pct = float(deep) / total * 100
        if rem is not None:
            sleep_rem_pct = float(rem) / total * 100
        if wake is not None:
            sleep_wake_pct = float(wake) / total * 100

        sleep_info_code = meta.get("info_code")

    # ── Quality flags
    sync_lag: float | None = None
    data_stale = False
    if last_sync_time is not None:
        sync_lag = (datetime.utcnow() - last_sync_time).total_seconds()
        data_stale = sync_lag > 1800  # >30 min

    hr_coverage = len(hr_values) / max(1, (window_end - window_start).total_seconds() / 60)
    hr_coverage = min(hr_coverage, 1.0)

    quality = QualityFlags(
        sync_lag_seconds=sync_lag,
        wearing_device=len(hr_values) >= _MIN_HR_POINTS if hr_values else None,
        hr_coverage_pct=hr_coverage if hr_values else 0.0,
        sleep_data_available=bool(sleep_readings),
        sleep_info_code=sleep_info_code,
        sufficient_baseline=baseline is not None and baseline.observation_count >= 7,
        data_staleness_warning=data_stale,
    )

    return FeatureWindow(
        participant_id=participant_id,
        window_start=window_start,
        window_end=window_end,
        window_duration_seconds=int((window_end - window_start).total_seconds()),
        activity_context=activity_ctx,
        steps_in_window=steps_in_window,
        calories_in_window=calories_in_window,
        mets_mean=mets_mean,
        azm_minutes=azm_minutes,
        hr_mean=hr_mean,
        hr_std=hr_std,
        hr_min=hr_min,
        hr_max=hr_max,
        hr_slope=hr_slope,
        hr_baseline_deviation=hr_baseline_dev,
        resting_hr=resting_hr,
        hrv_rmssd=hrv_rmssd,
        hrv_rmssd_baseline_deviation=hrv_rmssd_dev,
        hrv_deep_rmssd=hrv_deep_rmssd,
        breathing_rate=breathing_rate,
        br_baseline_deviation=br_dev,
        skin_temp_deviation=skin_temp_dev,
        spo2_avg=spo2_avg,
        spo2_min=spo2_min,
        sleep_duration_minutes=sleep_dur,
        sleep_efficiency=sleep_eff,
        sleep_deep_pct=sleep_deep_pct,
        sleep_rem_pct=sleep_rem_pct,
        sleep_wake_pct=sleep_wake_pct,
        sleep_wake_count=sleep_wake_count,
        quality=quality,
    )


# ── Baseline management ─────────────────────────────────────


def update_baseline_ewma(
    baseline: ParticipantBaseline,
    window: FeatureWindow,
) -> ParticipantBaseline:
    """Update personalised baselines via EWMA from a new feature window.

    Only updates fields where valid data is available.  The ``observation_count``
    is incremented to track calibration maturity.
    """
    alpha = baseline.ewma_alpha

    def _ewma(old: float | None, new: float | None) -> float | None:
        if new is None:
            return old
        if old is None:
            return new
        return alpha * new + (1 - alpha) * old

    def _ewma_std(old_std: float | None, old_mean: float | None, new_val: float | None) -> float | None:
        """Approximate running std via EWMA of squared deviations."""
        if new_val is None or old_mean is None:
            return old_std
        deviation_sq = (new_val - old_mean) ** 2
        if old_std is None:
            return math.sqrt(deviation_sq) if deviation_sq > 0 else 1.0
        old_var = old_std ** 2
        new_var = alpha * deviation_sq + (1 - alpha) * old_var
        return math.sqrt(new_var)

    # HR baselines by time-of-day (only at rest)
    if (
        window.hr_mean is not None
        and window.activity_context in (ActivityContext.REST, ActivityContext.LOW_MOVEMENT)
    ):
        band = get_time_of_day_band(window.window_start.hour)
        attr = f"hr_baseline_{band}"
        old_val = getattr(baseline, attr, None)
        setattr(baseline, attr, _ewma(old_val, window.hr_mean))

        baseline.hr_baseline_rest = _ewma(baseline.hr_baseline_rest, window.hr_mean)
        baseline.hr_std_baseline = _ewma_std(
            baseline.hr_std_baseline, baseline.hr_baseline_rest, window.hr_mean
        )

    # HRV (overnight)
    if window.hrv_rmssd is not None:
        baseline.hrv_rmssd_std = _ewma_std(
            baseline.hrv_rmssd_std, baseline.hrv_rmssd_baseline, window.hrv_rmssd
        )
        baseline.hrv_rmssd_baseline = _ewma(baseline.hrv_rmssd_baseline, window.hrv_rmssd)

    # Breathing rate
    if window.breathing_rate is not None:
        baseline.br_std = _ewma_std(
            baseline.br_std, baseline.br_baseline, window.breathing_rate
        )
        baseline.br_baseline = _ewma(baseline.br_baseline, window.breathing_rate)

    # Skin temperature (already relative, track baseline of relative)
    if window.skin_temp_deviation is not None:
        baseline.skin_temp_baseline = _ewma(
            baseline.skin_temp_baseline, window.skin_temp_deviation
        )

    # Sleep
    if window.sleep_duration_minutes is not None:
        baseline.sleep_duration_baseline = _ewma(
            baseline.sleep_duration_baseline, window.sleep_duration_minutes
        )
    if window.sleep_efficiency is not None:
        baseline.sleep_efficiency_baseline = _ewma(
            baseline.sleep_efficiency_baseline, window.sleep_efficiency
        )

    baseline.observation_count += 1
    baseline.updated_at = datetime.utcnow()
    return baseline
