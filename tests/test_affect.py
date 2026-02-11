"""Tests for the affect inference subsystem."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from wearable_agent.affect.ema import EMAScheduler, create_ema_label
from wearable_agent.affect.features import (
    classify_activity_context,
    extract_feature_window,
    get_time_of_day_band,
    update_baseline_ewma,
)
from wearable_agent.affect.inference import infer_affective_state
from wearable_agent.affect.models import (
    ActivityContext,
    AffectiveState,
    ArousalLevel,
    Confidence,
    DiscreteEmotion,
    EMALabel,
    FeatureWindow,
    InferenceOutput,
    ParticipantBaseline,
    QualityFlags,
    StressLevel,
    ValenceLevel,
)


# ── Activity context classification ──────────────────────────


class TestActivityContext:
    def test_rest_from_no_steps(self):
        ctx = classify_activity_context(steps=0, mets_mean=None, azm_minutes=None, hour=14)
        assert ctx == ActivityContext.REST

    def test_rest_from_low_mets(self):
        ctx = classify_activity_context(steps=3, mets_mean=1.2, azm_minutes=None, hour=10)
        assert ctx == ActivityContext.REST

    def test_low_movement(self):
        ctx = classify_activity_context(steps=30, mets_mean=None, azm_minutes=None, hour=10)
        assert ctx == ActivityContext.LOW_MOVEMENT

    def test_moderate_movement(self):
        ctx = classify_activity_context(steps=150, mets_mean=None, azm_minutes=None, hour=10)
        assert ctx == ActivityContext.MODERATE_MOVEMENT

    def test_high_movement_from_mets(self):
        ctx = classify_activity_context(steps=500, mets_mean=7.0, azm_minutes=5, hour=10)
        assert ctx == ActivityContext.HIGH_MOVEMENT

    def test_sleep_override(self):
        ctx = classify_activity_context(
            steps=0, mets_mean=1.0, azm_minutes=None, hour=3, sleep_period=True
        )
        assert ctx == ActivityContext.SLEEP


# ── Time-of-day bands ────────────────────────────────────────


class TestTimeOfDayBand:
    def test_morning(self):
        assert get_time_of_day_band(8) == "morning"

    def test_afternoon(self):
        assert get_time_of_day_band(14) == "afternoon"

    def test_evening(self):
        assert get_time_of_day_band(20) == "evening"

    def test_night(self):
        assert get_time_of_day_band(3) == "night"


# ── Feature extraction ───────────────────────────────────────


class TestFeatureExtraction:
    def test_empty_readings_produce_default_window(self):
        now = datetime.utcnow()
        fw = extract_feature_window(
            participant_id="P001",
            readings=[],
            window_start=now - timedelta(minutes=5),
            window_end=now,
        )
        assert fw.participant_id == "P001"
        assert fw.hr_mean is None
        # With no readings, steps=None → defaults to 0 → REST context
        assert fw.activity_context == ActivityContext.REST
        assert fw.quality.hr_coverage_pct == 0.0
        assert fw.quality.sufficient_baseline is False


# ── Baseline EWMA update ─────────────────────────────────────


class TestBaselineUpdate:
    def test_initial_baseline_sets_values(self):
        baseline = ParticipantBaseline(participant_id="P001", ewma_alpha=0.3)
        window = FeatureWindow(
            participant_id="P001",
            window_start=datetime(2026, 1, 10, 10, 0),
            window_end=datetime(2026, 1, 10, 10, 5),
            activity_context=ActivityContext.REST,
            hr_mean=72.0,
            hrv_rmssd=45.0,
            breathing_rate=16.0,
            sleep_duration_minutes=420.0,
            sleep_efficiency=88.0,
        )
        updated = update_baseline_ewma(baseline, window)
        assert updated.hr_baseline_morning == 72.0
        assert updated.hr_baseline_rest == 72.0
        assert updated.hrv_rmssd_baseline == 45.0
        assert updated.br_baseline == 16.0
        assert updated.sleep_duration_baseline == 420.0
        assert updated.observation_count == 1

    def test_ewma_smoothing(self):
        baseline = ParticipantBaseline(
            participant_id="P001",
            ewma_alpha=0.5,
            hr_baseline_rest=70.0,
            hr_baseline_morning=70.0,
            observation_count=5,
        )
        window = FeatureWindow(
            participant_id="P001",
            window_start=datetime(2026, 1, 10, 10, 0),
            window_end=datetime(2026, 1, 10, 10, 5),
            activity_context=ActivityContext.REST,
            hr_mean=80.0,
        )
        updated = update_baseline_ewma(baseline, window)
        # EWMA: 0.5 * 80 + 0.5 * 70 = 75
        assert updated.hr_baseline_rest == 75.0
        assert updated.hr_baseline_morning == 75.0

    def test_no_update_during_high_movement(self):
        baseline = ParticipantBaseline(
            participant_id="P001",
            hr_baseline_rest=70.0,
        )
        window = FeatureWindow(
            participant_id="P001",
            window_start=datetime(2026, 1, 10, 15, 0),
            window_end=datetime(2026, 1, 10, 15, 5),
            activity_context=ActivityContext.HIGH_MOVEMENT,
            hr_mean=140.0,
        )
        updated = update_baseline_ewma(baseline, window)
        # HR baseline should not change during high movement
        assert updated.hr_baseline_rest == 70.0


# ── Inference engine ──────────────────────────────────────────


class TestInference:
    def test_relaxed_state(self):
        fw = FeatureWindow(
            participant_id="P001",
            window_start=datetime(2026, 1, 10, 14, 0),
            window_end=datetime(2026, 1, 10, 14, 5),
            activity_context=ActivityContext.REST,
            hr_mean=62.0,
            hr_baseline_deviation=-0.5,  # below baseline → low arousal
            hrv_rmssd=55.0,
            hrv_rmssd_baseline_deviation=1.0,  # above baseline → relaxed
            breathing_rate=14.0,
            br_baseline_deviation=-0.3,
            sleep_efficiency=92.0,
            sleep_duration_minutes=480.0,
            sleep_wake_pct=5.0,
            quality=QualityFlags(sufficient_baseline=True),
        )
        output = infer_affective_state(fw)

        assert output.participant_id == "P001"
        assert output.state.arousal_score < 0.5  # low arousal
        assert output.state.stress_score < 0.5  # low stress
        assert output.state.arousal_confidence in (Confidence.MEDIUM, Confidence.HIGH)
        assert output.state.stress_confidence in (Confidence.MEDIUM, Confidence.HIGH)
        assert output.state.valence_confidence == Confidence.LOW
        assert len(output.contributing_signals) > 0
        assert output.explanation != ""

    def test_stressed_state(self):
        fw = FeatureWindow(
            participant_id="P001",
            window_start=datetime(2026, 1, 10, 14, 0),
            window_end=datetime(2026, 1, 10, 14, 5),
            activity_context=ActivityContext.REST,
            hr_mean=95.0,
            hr_baseline_deviation=2.5,  # well above baseline
            hrv_rmssd=18.0,
            hrv_rmssd_baseline_deviation=-2.0,  # well below baseline
            breathing_rate=22.0,
            br_baseline_deviation=2.0,
            sleep_efficiency=65.0,
            sleep_duration_minutes=300.0,
            sleep_wake_pct=25.0,
            quality=QualityFlags(sufficient_baseline=True),
        )
        output = infer_affective_state(fw)

        assert output.state.arousal_score > 0.5  # high arousal
        assert output.state.stress_score > 0.5  # high stress
        assert "hr_elevated_at_rest" in output.contributing_signals
        assert "hrv_below_baseline" in output.contributing_signals

    def test_activity_degrades_confidence(self):
        fw = FeatureWindow(
            participant_id="P001",
            window_start=datetime(2026, 1, 10, 14, 0),
            window_end=datetime(2026, 1, 10, 14, 5),
            activity_context=ActivityContext.HIGH_MOVEMENT,
            hr_mean=140.0,
            hr_baseline_deviation=3.0,
            quality=QualityFlags(sufficient_baseline=True),
        )
        output = infer_affective_state(fw)
        # During high movement, arousal confidence should be degraded
        assert output.activity_context == ActivityContext.HIGH_MOVEMENT
        assert "exercise" in output.explanation.lower() or "activity" in output.explanation.lower()

    def test_no_data_produces_defaults(self):
        fw = FeatureWindow(
            participant_id="P001",
            window_start=datetime(2026, 1, 10, 14, 0),
            window_end=datetime(2026, 1, 10, 14, 5),
        )
        output = infer_affective_state(fw)

        assert output.state.arousal_confidence == Confidence.VERY_LOW
        assert output.state.stress_confidence == Confidence.VERY_LOW
        assert output.state.dominant_emotion == DiscreteEmotion.UNKNOWN or \
               output.state.dominant_emotion == DiscreteEmotion.CALM

    def test_discrete_emotions_always_low_confidence(self):
        fw = FeatureWindow(
            participant_id="P001",
            window_start=datetime(2026, 1, 10, 14, 0),
            window_end=datetime(2026, 1, 10, 14, 5),
            activity_context=ActivityContext.REST,
            hr_mean=110.0,
            hr_baseline_deviation=3.0,
            hrv_rmssd=15.0,
            hrv_rmssd_baseline_deviation=-2.5,
            quality=QualityFlags(sufficient_baseline=True),
        )
        output = infer_affective_state(fw)

        for pred in output.state.discrete_emotions:
            # All discrete emotions should be LOW or VERY_LOW confidence
            assert pred.confidence in (Confidence.LOW, Confidence.VERY_LOW)

    def test_output_has_explanation(self):
        fw = FeatureWindow(
            participant_id="P001",
            window_start=datetime(2026, 1, 10, 14, 0),
            window_end=datetime(2026, 1, 10, 14, 5),
            activity_context=ActivityContext.REST,
            hr_mean=72.0,
            hr_baseline_deviation=0.3,
            quality=QualityFlags(sufficient_baseline=True),
        )
        output = infer_affective_state(fw)
        assert "Arousal:" in output.explanation
        assert "Stress:" in output.explanation
        assert "Valence:" in output.explanation


# ── EMA ───────────────────────────────────────────────────────


class TestEMA:
    def test_create_ema_label(self):
        label = create_ema_label(
            participant_id="P001",
            arousal=7,
            valence=3,
            stress=4,
            emotion_tag="anger",
            context_note="argument with colleague",
        )
        assert label.participant_id == "P001"
        assert label.arousal == 7
        assert label.valence == 3
        assert label.stress == 4
        assert label.emotion_tag == DiscreteEmotion.ANGER
        assert label.context_note == "argument with colleague"

    def test_invalid_emotion_tag_becomes_none(self):
        label = create_ema_label(
            participant_id="P001",
            emotion_tag="nonexistent_emotion",
        )
        assert label.emotion_tag is None

    def test_ema_scheduler_no_trigger_below_threshold(self):
        scheduler = EMAScheduler(stress_threshold=0.65)
        output = InferenceOutput(
            participant_id="P001",
            state=AffectiveState(stress_score=0.3),
            activity_context=ActivityContext.REST,
        )
        result = scheduler.should_trigger_event_prompt("P001", output)
        assert result["trigger"] is False

    def test_ema_scheduler_triggers_above_threshold(self):
        scheduler = EMAScheduler(stress_threshold=0.65)
        output = InferenceOutput(
            participant_id="P001",
            state=AffectiveState(stress_score=0.8),
            activity_context=ActivityContext.REST,
        )
        result = scheduler.should_trigger_event_prompt("P001", output)
        assert result["trigger"] is True

    def test_ema_scheduler_no_trigger_during_exercise(self):
        scheduler = EMAScheduler(stress_threshold=0.65)
        output = InferenceOutput(
            participant_id="P001",
            state=AffectiveState(stress_score=0.9),
            activity_context=ActivityContext.HIGH_MOVEMENT,
        )
        result = scheduler.should_trigger_event_prompt("P001", output)
        assert result["trigger"] is False
        assert "physical_activity" in result["reason"]

    def test_ema_scheduler_respects_daily_limit(self):
        scheduler = EMAScheduler(stress_threshold=0.3, max_daily=2)
        output = InferenceOutput(
            participant_id="P001",
            state=AffectiveState(stress_score=0.8),
            activity_context=ActivityContext.REST,
        )
        # Already at daily limit
        result = scheduler.should_trigger_event_prompt(
            "P001", output, daily_ema_count=2
        )
        assert result["trigger"] is False
        assert "daily_limit" in result["reason"]


# ── Models ────────────────────────────────────────────────────


class TestModels:
    def test_affective_state_defaults(self):
        state = AffectiveState()
        assert state.arousal_score == 0.5
        assert state.stress_score == 0.5
        assert state.valence_score == 0.5
        assert state.dominant_emotion == DiscreteEmotion.UNKNOWN

    def test_inference_output_serialisation(self):
        output = InferenceOutput(
            participant_id="P001",
            state=AffectiveState(
                arousal_score=0.7,
                stress_score=0.6,
            ),
            contributing_signals=["hr_elevated_at_rest", "hrv_below_baseline"],
            explanation="Test explanation",
            top_features={"hr_baseline_z": 2.1},
        )
        data = output.model_dump(mode="json")
        assert data["participant_id"] == "P001"
        assert data["state"]["arousal_score"] == 0.7
        assert len(data["contributing_signals"]) == 2
        assert data["top_features"]["hr_baseline_z"] == 2.1

    def test_quality_flags(self):
        q = QualityFlags(
            sync_lag_seconds=900,
            wearing_device=True,
            hr_coverage_pct=0.85,
            sufficient_baseline=True,
        )
        assert q.data_staleness_warning is False

    def test_feature_window_defaults(self):
        fw = FeatureWindow(
            participant_id="P001",
            window_start=datetime(2026, 1, 10, 10, 0),
            window_end=datetime(2026, 1, 10, 10, 5),
        )
        assert fw.activity_context == ActivityContext.UNKNOWN
        assert fw.hr_mean is None
        assert fw.quality.sufficient_baseline is False
