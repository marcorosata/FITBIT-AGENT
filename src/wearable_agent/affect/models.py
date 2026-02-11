"""Pydantic models for the affective inference subsystem.

These models represent:
- Dimensional affect (arousal, valence, stress)
- Discrete emotion predictions with confidence bounds
- Feature windows and quality metadata
- EMA (Ecological Momentary Assessment) labels for ground-truth
- Inference output with explainability fields
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────


class Confidence(str, Enum):
    """Confidence tier for an affective inference output.

    Based on evidence quality: signal availability, activity context,
    recency, and personalisation state.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


class ArousalLevel(str, Enum):
    """Discretised arousal (physiological activation) level."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class StressLevel(str, Enum):
    """Discretised stress / recovery level."""

    RELAXED = "relaxed"
    LOW_STRESS = "low_stress"
    MODERATE_STRESS = "moderate_stress"
    HIGH_STRESS = "high_stress"
    VERY_HIGH_STRESS = "very_high_stress"


class ValenceLevel(str, Enum):
    """Coarse valence estimate (positive / negative affect tendency)."""

    NEGATIVE = "negative"
    SLIGHTLY_NEGATIVE = "slightly_negative"
    NEUTRAL = "neutral"
    SLIGHTLY_POSITIVE = "slightly_positive"
    POSITIVE = "positive"


class DiscreteEmotion(str, Enum):
    """Basic emotion categories (Ekman + calm).

    Classification confidence is inherently low for ANS-only inference.
    """

    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    DISGUST = "disgust"
    SURPRISE = "surprise"
    CALM = "calm"
    UNKNOWN = "unknown"


class ActivityContext(str, Enum):
    """Activity context label used to control for physical-activity confounders."""

    REST = "rest"  # steps/METs indicate sedentary
    LOW_MOVEMENT = "low_movement"
    MODERATE_MOVEMENT = "moderate_movement"
    HIGH_MOVEMENT = "high_movement"
    SLEEP = "sleep"
    UNKNOWN = "unknown"


# ── Quality & context ────────────────────────────────────────


class QualityFlags(BaseModel):
    """Data-quality metadata attached to every inference output."""

    sync_lag_seconds: float | None = Field(
        None,
        description="Seconds since last device sync (from Get Devices).",
    )
    wearing_device: bool | None = Field(
        None,
        description="Whether the device appears to be on-wrist (inferred).",
    )
    hr_coverage_pct: float | None = Field(
        None,
        description="Fraction of the feature window with valid HR readings.",
    )
    sleep_data_available: bool = Field(
        False,
        description="Whether overnight sleep/HRV/BR data is available for today.",
    )
    sleep_info_code: int | None = Field(
        None,
        description="Fitbit sleep infoCode (0 = good, >0 = degraded quality).",
    )
    sufficient_baseline: bool = Field(
        False,
        description="Whether enough history exists for personalised baseline.",
    )
    data_staleness_warning: bool = Field(
        False,
        description="True if data may be stale (sync_lag > threshold).",
    )


# ── Feature windows ──────────────────────────────────────────


class FeatureWindow(BaseModel):
    """Aggregated features over a time window for a single participant.

    Features are normalised relative to personalised baselines where
    available.  Missing values are represented as ``None``.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    participant_id: str
    window_start: datetime
    window_end: datetime
    window_duration_seconds: int = 300  # default 5 min

    # ── Activity context
    activity_context: ActivityContext = ActivityContext.UNKNOWN
    steps_in_window: float | None = None
    calories_in_window: float | None = None
    mets_mean: float | None = None
    azm_minutes: float | None = None

    # ── Heart rate features
    hr_mean: float | None = None
    hr_std: float | None = None
    hr_min: float | None = None
    hr_max: float | None = None
    hr_slope: float | None = None  # linear trend over window
    hr_baseline_deviation: float | None = None  # z-score vs personal baseline
    resting_hr: float | None = None

    # ── HRV features (typically overnight)
    hrv_rmssd: float | None = None
    hrv_rmssd_baseline_deviation: float | None = None
    hrv_deep_rmssd: float | None = None
    hrv_lf: float | None = None
    hrv_hf: float | None = None
    hrv_lf_hf_ratio: float | None = None

    # ── Breathing rate (typically overnight)
    breathing_rate: float | None = None
    br_baseline_deviation: float | None = None

    # ── Skin temperature (nightly relative)
    skin_temp_deviation: float | None = None

    # ── SpO₂ (overnight)
    spo2_avg: float | None = None
    spo2_min: float | None = None

    # ── Sleep features (from last night)
    sleep_duration_minutes: float | None = None
    sleep_efficiency: float | None = None
    sleep_deep_pct: float | None = None
    sleep_rem_pct: float | None = None
    sleep_wake_pct: float | None = None
    sleep_wake_count: int | None = None

    # ── Quality
    quality: QualityFlags = Field(default_factory=QualityFlags)


# ── Affective state ──────────────────────────────────────────


class EmotionPrediction(BaseModel):
    """A single discrete-emotion prediction with probability."""

    emotion: DiscreteEmotion
    probability: float = Field(ge=0.0, le=1.0)
    confidence: Confidence = Confidence.LOW


class AffectiveState(BaseModel):
    """Dimensional + discrete affective state estimate for a participant.

    This is the primary output of the inference engine.  All scores are
    probabilistic estimates, never diagnoses.
    """

    # ── Dimensional affect
    arousal_score: float = Field(
        0.5, ge=0.0, le=1.0,
        description="Arousal / activation score [0=very low, 1=very high].",
    )
    arousal_level: ArousalLevel = ArousalLevel.MODERATE
    arousal_confidence: Confidence = Confidence.MEDIUM

    stress_score: float = Field(
        0.5, ge=0.0, le=1.0,
        description="Stress vs relaxation score [0=relaxed, 1=very stressed].",
    )
    stress_level: StressLevel = StressLevel.MODERATE_STRESS
    stress_confidence: Confidence = Confidence.MEDIUM

    valence_score: float = Field(
        0.5, ge=0.0, le=1.0,
        description="Valence / pleasantness score [0=negative, 1=positive].",
    )
    valence_level: ValenceLevel = ValenceLevel.NEUTRAL
    valence_confidence: Confidence = Confidence.LOW

    # ── Discrete emotions (optional, low confidence by default)
    discrete_emotions: list[EmotionPrediction] = Field(default_factory=list)

    # ── Metadata
    dominant_emotion: DiscreteEmotion = DiscreteEmotion.UNKNOWN
    dominant_emotion_confidence: Confidence = Confidence.VERY_LOW


# ── Inference output ──────────────────────────────────────────


class InferenceOutput(BaseModel):
    """Full inference result persisted to the database.

    Includes the affective state, the feature window it was derived from,
    quality flags, and explainability fields.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    participant_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # ── Core result
    state: AffectiveState = Field(default_factory=AffectiveState)
    feature_window_id: str | None = None
    activity_context: ActivityContext = ActivityContext.UNKNOWN

    # ── Explainability
    contributing_signals: list[str] = Field(
        default_factory=list,
        description=(
            "Which Fitbit signals contributed to this inference "
            "(e.g. 'hr_elevated_at_rest', 'hrv_below_baseline')."
        ),
    )
    explanation: str = Field(
        "",
        description="Human-readable explanation of the inference rationale.",
    )
    top_features: dict[str, float] = Field(
        default_factory=dict,
        description="Top feature name → value pairs that drove the score.",
    )

    # ── Quality
    quality: QualityFlags = Field(default_factory=QualityFlags)

    # ── Model
    model_version: str = "rule_v1"


# ── EMA ───────────────────────────────────────────────────────


class EMALabel(BaseModel):
    """Ecological Momentary Assessment self-report label.

    Ground truth for calibration and validation of affect inference.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    participant_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # ── Self-report (SAM-style 1-9 or 1-5 scales)
    arousal: int | None = Field(None, ge=1, le=9, description="Self-rated arousal (1=calm, 9=excited).")
    valence: int | None = Field(None, ge=1, le=9, description="Self-rated valence (1=unpleasant, 9=pleasant).")
    stress: int | None = Field(None, ge=1, le=5, description="Self-rated stress (1=none, 5=extreme).")
    emotion_tag: DiscreteEmotion | None = Field(None, description="Self-labelled discrete emotion.")

    # ── Context
    context_note: str = Field("", description="Free-text context (e.g. 'in meeting', 'after coffee').")
    trigger: str = Field(
        "scheduled",
        description="What triggered this EMA: 'scheduled', 'event_based', 'user_initiated'.",
    )

    # ── Linking
    inference_output_id: str | None = Field(
        None,
        description="ID of the inference output that triggered this EMA (if event-based).",
    )


# ── Participant baseline ─────────────────────────────────────


class ParticipantBaseline(BaseModel):
    """Personalised physiological baselines, updated via EWMA.

    Baselines are segmented by time-of-day band and activity context
    to account for circadian variation.
    """

    participant_id: str
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # ── HR baselines (by time-of-day)
    hr_baseline_morning: float | None = None  # 06:00–12:00
    hr_baseline_afternoon: float | None = None  # 12:00–18:00
    hr_baseline_evening: float | None = None  # 18:00–00:00
    hr_baseline_night: float | None = None  # 00:00–06:00
    hr_baseline_rest: float | None = None  # at rest (low movement)
    hr_std_baseline: float | None = None  # population std for z-scoring

    # ── HRV baselines (overnight)
    hrv_rmssd_baseline: float | None = None
    hrv_rmssd_std: float | None = None

    # ── Breathing rate baseline (overnight)
    br_baseline: float | None = None
    br_std: float | None = None

    # ── Skin temperature baseline
    skin_temp_baseline: float | None = None  # Already relative in Fitbit

    # ── Sleep baselines
    sleep_duration_baseline: float | None = None
    sleep_efficiency_baseline: float | None = None

    # ── EWMA smoothing factor
    ewma_alpha: float = Field(
        0.1,
        description="Exponential smoothing factor for baseline updates.",
    )
    observation_count: int = 0
