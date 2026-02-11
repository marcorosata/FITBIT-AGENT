"""Affect inference engine — evidence-based arousal / stress / valence scoring.

This module implements the core inference logic that maps physiological
features (from :class:`FeatureWindow`) to affective state estimates
(:class:`InferenceOutput`).

Design principles
-----------------
- **Conservative & evidence-based**: confidence levels reflect the actual
  precision achievable with Fitbit Web API signals (no EDA, no raw
  PPG/IBI, many metrics overnight-only).
- **Activity-controlled**: arousal/stress scores are only computed at
  medium+ confidence when physical activity confounders are controlled
  (rest/low-movement windows).
- **Explainable**: every inference output lists the contributing signals
  and a human-readable explanation.
- **Personalised**: z-score deviations from participant baselines are
  preferred over absolute thresholds where baselines are available.
- **Probabilistic framing**: outputs are estimates with confidence tiers,
  never diagnoses.

Evidence mapping (from specification)
-------------------------------------
=================  ==============================================  ==============
Construct          Key signals                                     Confidence
=================  ==============================================  ==============
Arousal            HR ↑ vs baseline (at rest), BR ↑, temp ↓        Medium
Stress             HR ↑ sustained + HRV ↓ + sleep fragmentation    Medium–High
Relaxation         HR ↓/stable + HRV ↑ + efficient sleep           Medium
Valence            Indirect via sleep quality / HRV trends          Low
Discrete emotions  Arousal + valence heuristic                      Very Low–Low
=================  ==============================================  ==============
"""

from __future__ import annotations

from datetime import datetime

import structlog

from wearable_agent.affect.models import (
    ActivityContext,
    AffectiveState,
    ArousalLevel,
    Confidence,
    DiscreteEmotion,
    EmotionPrediction,
    FeatureWindow,
    InferenceOutput,
    StressLevel,
    ValenceLevel,
)

logger = structlog.get_logger(__name__)

# ── Score thresholds ──────────────────────────────────────────

_AROUSAL_THRESHOLDS = {
    ArousalLevel.VERY_LOW: (0.0, 0.15),
    ArousalLevel.LOW: (0.15, 0.35),
    ArousalLevel.MODERATE: (0.35, 0.65),
    ArousalLevel.HIGH: (0.65, 0.85),
    ArousalLevel.VERY_HIGH: (0.85, 1.01),
}

_STRESS_THRESHOLDS = {
    StressLevel.RELAXED: (0.0, 0.15),
    StressLevel.LOW_STRESS: (0.15, 0.35),
    StressLevel.MODERATE_STRESS: (0.35, 0.60),
    StressLevel.HIGH_STRESS: (0.60, 0.80),
    StressLevel.VERY_HIGH_STRESS: (0.80, 1.01),
}

_VALENCE_THRESHOLDS = {
    ValenceLevel.NEGATIVE: (0.0, 0.20),
    ValenceLevel.SLIGHTLY_NEGATIVE: (0.20, 0.40),
    ValenceLevel.NEUTRAL: (0.40, 0.60),
    ValenceLevel.SLIGHTLY_POSITIVE: (0.60, 0.80),
    ValenceLevel.POSITIVE: (0.80, 1.01),
}


def _score_to_level(score: float, thresholds: dict) -> str:
    """Map a 0-1 score to a categorical level using thresholds."""
    for level, (lo, hi) in thresholds.items():
        if lo <= score < hi:
            return level
    return list(thresholds.keys())[-1]


# ── Arousal scoring ──────────────────────────────────────────


def _compute_arousal(
    fw: FeatureWindow,
) -> tuple[float, Confidence, list[str], dict[str, float]]:
    """Compute arousal score from feature window.

    Returns (score, confidence, contributing_signals, top_features).
    """
    signals: list[str] = []
    features: dict[str, float] = {}
    components: list[float] = []
    weights: list[float] = []

    # 1. HR baseline deviation (strongest signal at rest)
    if fw.hr_baseline_deviation is not None and fw.activity_context in (
        ActivityContext.REST, ActivityContext.LOW_MOVEMENT
    ):
        z = fw.hr_baseline_deviation
        # Map z-score to 0-1: z=0 → 0.5, z=+2 → ~0.88, z=-2 → ~0.12
        hr_component = _sigmoid(z, k=1.0)
        components.append(hr_component)
        weights.append(3.0)
        features["hr_baseline_z"] = round(z, 2)
        if z > 1.0:
            signals.append("hr_elevated_at_rest")
        elif z < -1.0:
            signals.append("hr_low_at_rest")

    elif fw.hr_mean is not None:
        # Absolute HR heuristic (no baseline): weaker signal
        # Resting: 60-100 normal, >100 elevated, <50 very low
        if fw.activity_context in (ActivityContext.REST, ActivityContext.LOW_MOVEMENT):
            hr_norm = max(0.0, min(1.0, (fw.hr_mean - 50) / 80))
            components.append(hr_norm)
            weights.append(1.5)
            features["hr_mean"] = round(fw.hr_mean, 1)
            if fw.hr_mean > 100:
                signals.append("hr_elevated_absolute")

    # 2. HR slope (trend within window)
    if fw.hr_slope is not None and abs(fw.hr_slope) > 0.5:
        slope_component = _sigmoid(fw.hr_slope, k=0.5)
        components.append(slope_component)
        weights.append(1.0)
        features["hr_slope"] = round(fw.hr_slope, 3)
        if fw.hr_slope > 1.0:
            signals.append("hr_rising_trend")

    # 3. Breathing rate deviation (overnight, proxy for sustained arousal)
    if fw.br_baseline_deviation is not None:
        br_z = fw.br_baseline_deviation
        br_component = _sigmoid(br_z, k=0.8)
        components.append(br_component)
        weights.append(1.5)
        features["br_baseline_z"] = round(br_z, 2)
        if br_z > 1.0:
            signals.append("breathing_rate_elevated")

    # 4. Skin temperature deviation (overnight, stress → vasoconstriction → ↓)
    if fw.skin_temp_deviation is not None:
        # Inverted: stress causes temp drop
        temp_component = _sigmoid(-fw.skin_temp_deviation, k=1.0)
        components.append(temp_component)
        weights.append(0.8)
        features["skin_temp_dev"] = round(fw.skin_temp_deviation, 2)
        if fw.skin_temp_deviation < -1.0:
            signals.append("skin_temp_drop")

    # Compute weighted average
    if not components:
        return 0.5, Confidence.VERY_LOW, signals, features

    total_weight = sum(weights)
    score = sum(c * w for c, w in zip(components, weights)) / total_weight
    score = max(0.0, min(1.0, score))

    # Determine confidence
    n_signals = len(components)
    if (
        fw.activity_context in (ActivityContext.REST, ActivityContext.LOW_MOVEMENT)
        and fw.hr_baseline_deviation is not None
        and n_signals >= 2
    ):
        confidence = Confidence.MEDIUM
    elif n_signals >= 1 and fw.activity_context in (
        ActivityContext.REST, ActivityContext.LOW_MOVEMENT
    ):
        confidence = Confidence.MEDIUM
    elif n_signals >= 1:
        confidence = Confidence.LOW
    else:
        confidence = Confidence.VERY_LOW

    return score, confidence, signals, features


# ── Stress scoring ───────────────────────────────────────────


def _compute_stress(
    fw: FeatureWindow,
) -> tuple[float, Confidence, list[str], dict[str, float]]:
    """Compute stress score from feature window.

    Stress uses a broader set of signals including overnight metrics
    (HRV, sleep quality) that indicate allostatic load.

    Returns (score, confidence, contributing_signals, top_features).
    """
    signals: list[str] = []
    features: dict[str, float] = {}
    components: list[float] = []
    weights: list[float] = []

    # 1. HRV — lower HRV = higher stress (strongest overnight signal)
    if fw.hrv_rmssd_baseline_deviation is not None:
        z = fw.hrv_rmssd_baseline_deviation
        # Inverted: low HRV → high stress
        hrv_component = _sigmoid(-z, k=1.0)
        components.append(hrv_component)
        weights.append(3.0)
        features["hrv_baseline_z"] = round(z, 2)
        if z < -1.0:
            signals.append("hrv_below_baseline")
        elif z > 1.0:
            signals.append("hrv_above_baseline")

    elif fw.hrv_rmssd is not None:
        # Absolute HRV heuristic: <20ms high stress, >60ms relaxed
        hrv_norm = max(0.0, min(1.0, 1.0 - (fw.hrv_rmssd - 15) / 60))
        components.append(hrv_norm)
        weights.append(2.0)
        features["hrv_rmssd"] = round(fw.hrv_rmssd, 1)
        if fw.hrv_rmssd < 20:
            signals.append("hrv_very_low_absolute")

    # 2. HR at rest (elevated HR at rest = stress indicator)
    if fw.hr_baseline_deviation is not None and fw.activity_context in (
        ActivityContext.REST, ActivityContext.LOW_MOVEMENT,
    ):
        z = fw.hr_baseline_deviation
        hr_stress = _sigmoid(z, k=0.8)
        components.append(hr_stress)
        weights.append(2.5)
        features["hr_rest_z"] = round(z, 2)
        if z > 1.5:
            signals.append("hr_sustained_elevation")

    # 3. Sleep quality — poor sleep = higher allostatic load
    sleep_stress = _compute_sleep_stress_component(fw)
    if sleep_stress is not None:
        components.append(sleep_stress[0])
        weights.append(2.0)
        signals.extend(sleep_stress[1])
        features.update(sleep_stress[2])

    # 4. Breathing rate (overnight)
    if fw.br_baseline_deviation is not None:
        br_z = fw.br_baseline_deviation
        br_stress = _sigmoid(br_z, k=0.8)
        components.append(br_stress)
        weights.append(1.5)
        features["br_stress_z"] = round(br_z, 2)
        if br_z > 1.0:
            signals.append("br_elevated_overnight")

    # 5. Skin temperature
    if fw.skin_temp_deviation is not None:
        temp_stress = _sigmoid(-fw.skin_temp_deviation, k=0.6)
        components.append(temp_stress)
        weights.append(0.8)

    # Compute weighted average
    if not components:
        return 0.5, Confidence.VERY_LOW, signals, features

    total_weight = sum(weights)
    score = sum(c * w for c, w in zip(components, weights)) / total_weight
    score = max(0.0, min(1.0, score))

    # Determine confidence — stress has more supporting evidence
    n_overnight = sum(1 for s in signals if any(
        kw in s for kw in ("hrv", "sleep", "br_elevated")
    ))
    n_daytime = sum(1 for s in signals if "hr_" in s)
    total_signals = len(components)

    if total_signals >= 3 and n_overnight >= 1:
        confidence = Confidence.HIGH
    elif total_signals >= 2:
        confidence = Confidence.MEDIUM
    elif total_signals >= 1:
        confidence = Confidence.LOW
    else:
        confidence = Confidence.VERY_LOW

    return score, confidence, signals, features


def _compute_sleep_stress_component(
    fw: FeatureWindow,
) -> tuple[float, list[str], dict[str, float]] | None:
    """Compute sleep-based stress sub-component."""
    signals: list[str] = []
    features: dict[str, float] = {}
    components: list[float] = []

    if fw.sleep_efficiency is not None:
        # Lower efficiency → more stress
        eff_stress = max(0.0, min(1.0, 1.0 - fw.sleep_efficiency / 100))
        components.append(eff_stress)
        features["sleep_efficiency"] = round(fw.sleep_efficiency, 1)
        if fw.sleep_efficiency < 75:
            signals.append("sleep_poor_efficiency")

    if fw.sleep_wake_pct is not None:
        # High wake % → fragmented → stress
        wake_stress = max(0.0, min(1.0, fw.sleep_wake_pct / 30))
        components.append(wake_stress)
        features["sleep_wake_pct"] = round(fw.sleep_wake_pct, 1)
        if fw.sleep_wake_pct > 15:
            signals.append("sleep_fragmented")

    if fw.sleep_duration_minutes is not None:
        # Very short sleep → stress (< 5h = high, > 8h = low)
        dur_hours = fw.sleep_duration_minutes / 60
        dur_stress = max(0.0, min(1.0, 1.0 - (dur_hours - 4) / 5))
        components.append(dur_stress)
        features["sleep_hours"] = round(dur_hours, 1)
        if dur_hours < 5:
            signals.append("sleep_very_short")
        elif dur_hours < 6:
            signals.append("sleep_short")

    if not components:
        return None
    return (sum(components) / len(components), signals, features)


# ── Valence scoring ──────────────────────────────────────────


def _compute_valence(
    fw: FeatureWindow,
    arousal_score: float,
    stress_score: float,
) -> tuple[float, Confidence, list[str], dict[str, float]]:
    """Estimate valence (positive/negative affect) — inherently low confidence.

    Without EDA, facial expression, or self-report context, valence is
    the weakest dimension.  We use indirect proxies:
    - Good sleep + high HRV → positive valence tendency
    - High stress → negative valence tendency
    - Activity at rest with low HR → possible calm positive

    Returns (score, confidence, contributing_signals, top_features).
    """
    signals: list[str] = []
    features: dict[str, float] = {}
    components: list[float] = []
    weights: list[float] = []

    # 1. Inverse stress → valence proxy (strongest available signal)
    inverse_stress = 1.0 - stress_score
    components.append(inverse_stress)
    weights.append(2.0)
    features["inverse_stress"] = round(inverse_stress, 2)

    # 2. HRV trend (higher → better regulation → positive tendency)
    if fw.hrv_rmssd_baseline_deviation is not None:
        z = fw.hrv_rmssd_baseline_deviation
        hrv_valence = _sigmoid(z, k=0.5)
        components.append(hrv_valence)
        weights.append(1.5)
        if z > 1.0:
            signals.append("hrv_high_positive_tendency")

    # 3. Sleep quality (good sleep → positive mood tendency)
    if fw.sleep_efficiency is not None and fw.sleep_duration_minutes is not None:
        dur_h = fw.sleep_duration_minutes / 60
        sleep_quality = min(1.0, (fw.sleep_efficiency / 100) * min(1.0, dur_h / 7))
        components.append(sleep_quality)
        weights.append(1.5)
        features["sleep_quality_proxy"] = round(sleep_quality, 2)
        if sleep_quality > 0.7:
            signals.append("good_sleep_positive_tendency")
        elif sleep_quality < 0.3:
            signals.append("poor_sleep_negative_tendency")

    if not components:
        return 0.5, Confidence.VERY_LOW, signals, features

    total_weight = sum(weights)
    score = sum(c * w for c, w in zip(components, weights)) / total_weight
    score = max(0.0, min(1.0, score))

    # Valence is ALWAYS low confidence from physiology alone
    confidence = Confidence.LOW
    if not signals:
        confidence = Confidence.VERY_LOW

    return score, confidence, signals, features


# ── Discrete emotion mapping ────────────────────────────────


def _map_discrete_emotions(
    arousal_score: float,
    valence_score: float,
    stress_score: float,
    activity_context: ActivityContext,
) -> tuple[list[EmotionPrediction], DiscreteEmotion, Confidence]:
    """Map dimensional affect to discrete emotion probabilities.

    This is inherently low confidence: the same arousal/valence
    combination can correspond to many different emotions.
    The mapping follows a Russell circumplex-inspired heuristic.

    Returns (predictions, dominant_emotion, confidence).
    """
    predictions: list[EmotionPrediction] = []

    # Heuristic probability distributions
    if arousal_score < 0.3 and valence_score > 0.6:
        # Low arousal + positive → calm/contentment
        predictions = [
            EmotionPrediction(emotion=DiscreteEmotion.CALM, probability=0.5, confidence=Confidence.LOW),
            EmotionPrediction(emotion=DiscreteEmotion.JOY, probability=0.2, confidence=Confidence.VERY_LOW),
            EmotionPrediction(emotion=DiscreteEmotion.SADNESS, probability=0.05, confidence=Confidence.VERY_LOW),
        ]
    elif arousal_score < 0.3 and valence_score < 0.4:
        # Low arousal + negative → sadness tendency
        predictions = [
            EmotionPrediction(emotion=DiscreteEmotion.SADNESS, probability=0.35, confidence=Confidence.LOW),
            EmotionPrediction(emotion=DiscreteEmotion.CALM, probability=0.25, confidence=Confidence.VERY_LOW),
        ]
    elif arousal_score > 0.7 and valence_score < 0.3:
        # High arousal + negative → fear/anger
        predictions = [
            EmotionPrediction(emotion=DiscreteEmotion.FEAR, probability=0.3, confidence=Confidence.LOW),
            EmotionPrediction(emotion=DiscreteEmotion.ANGER, probability=0.3, confidence=Confidence.LOW),
        ]
    elif arousal_score > 0.7 and valence_score > 0.6:
        # High arousal + positive → joy/excitement
        predictions = [
            EmotionPrediction(emotion=DiscreteEmotion.JOY, probability=0.4, confidence=Confidence.LOW),
            EmotionPrediction(emotion=DiscreteEmotion.SURPRISE, probability=0.2, confidence=Confidence.VERY_LOW),
        ]
    elif stress_score > 0.7:
        # High stress regardless → stress-related emotions
        predictions = [
            EmotionPrediction(emotion=DiscreteEmotion.FEAR, probability=0.25, confidence=Confidence.LOW),
            EmotionPrediction(emotion=DiscreteEmotion.ANGER, probability=0.2, confidence=Confidence.VERY_LOW),
        ]
    else:
        # Ambiguous → unknown/calm
        predictions = [
            EmotionPrediction(emotion=DiscreteEmotion.CALM, probability=0.3, confidence=Confidence.VERY_LOW),
            EmotionPrediction(emotion=DiscreteEmotion.UNKNOWN, probability=0.3, confidence=Confidence.VERY_LOW),
        ]

    # Sort by probability
    predictions.sort(key=lambda p: p.probability, reverse=True)
    dominant = predictions[0].emotion if predictions else DiscreteEmotion.UNKNOWN
    dominant_conf = predictions[0].confidence if predictions else Confidence.VERY_LOW

    return predictions, dominant, dominant_conf


# ── Main inference function ──────────────────────────────────


def infer_affective_state(fw: FeatureWindow) -> InferenceOutput:
    """Run the full inference pipeline on a feature window.

    This is the primary entry point.  It computes arousal, stress,
    valence, and discrete-emotion estimates, attaches explainability
    fields, and returns a complete :class:`InferenceOutput`.

    Parameters
    ----------
    fw
        A fully populated :class:`FeatureWindow` with quality flags.

    Returns
    -------
    InferenceOutput
        Complete inference result ready for persistence and API delivery.
    """
    all_signals: list[str] = []
    all_features: dict[str, float] = {}

    # 1. Arousal
    arousal_score, arousal_conf, a_signals, a_features = _compute_arousal(fw)
    all_signals.extend(a_signals)
    all_features.update(a_features)

    # 2. Stress
    stress_score, stress_conf, s_signals, s_features = _compute_stress(fw)
    all_signals.extend(s_signals)
    all_features.update(s_features)

    # 3. Valence
    valence_score, valence_conf, v_signals, v_features = _compute_valence(
        fw, arousal_score, stress_score
    )
    all_signals.extend(v_signals)
    all_features.update(v_features)

    # 4. Discrete emotions
    emotions, dominant, dominant_conf = _map_discrete_emotions(
        arousal_score, valence_score, stress_score, fw.activity_context
    )

    # ── Build affective state
    state = AffectiveState(
        arousal_score=round(arousal_score, 3),
        arousal_level=_score_to_level(arousal_score, _AROUSAL_THRESHOLDS),
        arousal_confidence=arousal_conf,
        stress_score=round(stress_score, 3),
        stress_level=_score_to_level(stress_score, _STRESS_THRESHOLDS),
        stress_confidence=stress_conf,
        valence_score=round(valence_score, 3),
        valence_level=_score_to_level(valence_score, _VALENCE_THRESHOLDS),
        valence_confidence=valence_conf,
        discrete_emotions=emotions,
        dominant_emotion=dominant,
        dominant_emotion_confidence=dominant_conf,
    )

    # ── Explanation
    explanation = _build_explanation(state, all_signals, fw)

    # Deduplicate signals
    unique_signals = list(dict.fromkeys(all_signals))

    output = InferenceOutput(
        participant_id=fw.participant_id,
        timestamp=fw.window_end,
        state=state,
        feature_window_id=fw.id,
        activity_context=fw.activity_context,
        contributing_signals=unique_signals,
        explanation=explanation,
        top_features=all_features,
        quality=fw.quality,
        model_version="rule_v1",
    )

    logger.info(
        "affect.inference_complete",
        participant=fw.participant_id,
        arousal=round(arousal_score, 2),
        stress=round(stress_score, 2),
        valence=round(valence_score, 2),
        confidence_arousal=arousal_conf.value,
        confidence_stress=stress_conf.value,
        activity=fw.activity_context.value,
        n_signals=len(unique_signals),
    )
    return output


# ── Helpers ───────────────────────────────────────────────────


def _sigmoid(x: float, k: float = 1.0, midpoint: float = 0.0) -> float:
    """Logistic sigmoid mapping: maps R → (0, 1). Used to convert z-scores
    and deviations into normalised 0-1 component scores.

    Parameters
    ----------
    x : float
        Input value (e.g., z-score).
    k : float
        Steepness parameter.  Higher k → sharper transition.
    midpoint : float
        Value of x where output = 0.5.
    """
    import math

    try:
        return 1.0 / (1.0 + math.exp(-k * (x - midpoint)))
    except OverflowError:
        return 0.0 if x < midpoint else 1.0


def _build_explanation(
    state: AffectiveState,
    signals: list[str],
    fw: FeatureWindow,
) -> str:
    """Generate a human-readable explanation of the inference."""
    parts: list[str] = []

    # Context
    parts.append(f"Activity context: {fw.activity_context.value}.")

    # Arousal
    parts.append(
        f"Arousal: {state.arousal_level.value} ({state.arousal_score:.2f}), "
        f"confidence {state.arousal_confidence.value}."
    )

    # Stress
    parts.append(
        f"Stress: {state.stress_level.value} ({state.stress_score:.2f}), "
        f"confidence {state.stress_confidence.value}."
    )

    # Valence
    parts.append(
        f"Valence: {state.valence_level.value} ({state.valence_score:.2f}), "
        f"confidence {state.valence_confidence.value}."
    )

    # Contributing signals
    if signals:
        parts.append(f"Contributing signals: {', '.join(signals)}.")

    # Quality warning
    if fw.quality.data_staleness_warning:
        parts.append("⚠ Data may be stale (sync lag > 30 min).")
    if not fw.quality.sufficient_baseline:
        parts.append("ℹ Personalised baseline not yet calibrated (< 7 days of data).")
    if fw.activity_context in (ActivityContext.HIGH_MOVEMENT, ActivityContext.MODERATE_MOVEMENT):
        parts.append(
            "⚠ Physical activity detected — arousal/stress estimates may reflect "
            "exercise rather than emotional state."
        )

    # Discrete emotion caveat
    if state.discrete_emotions:
        parts.append(
            f"Dominant emotion estimate: {state.dominant_emotion.value} "
            f"(confidence: {state.dominant_emotion_confidence.value}). "
            "Note: discrete emotion classification from wearable physiology "
            "alone has inherently low accuracy."
        )

    return " ".join(parts)
