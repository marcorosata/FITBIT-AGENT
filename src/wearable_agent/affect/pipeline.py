"""Affect pipeline orchestrator — ties feature extraction, inference, and EMA.

This module provides the high-level :class:`AffectPipeline` that is wired
into the FastAPI lifespan and the agent.  It coordinates:

1. Building feature windows from recent sensor readings
2. Loading / updating personalised baselines
3. Running the inference engine
4. Persisting results
5. Triggering event-based EMA prompts
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from wearable_agent.affect.ema import EMAScheduler
from wearable_agent.affect.features import extract_feature_window, update_baseline_ewma
from wearable_agent.affect.inference import infer_affective_state
from wearable_agent.affect.models import (
    InferenceOutput,
    ParticipantBaseline,
)
from wearable_agent.models import MetricType
from wearable_agent.storage.repository import (
    BaselineRepository,
    EMARepository,
    FeatureWindowRepository,
    InferenceOutputRepository,
    ReadingRepository,
)

logger = structlog.get_logger(__name__)

# Overnight metrics to fetch for feature windows
_OVERNIGHT_METRICS = [
    MetricType.HRV,
    MetricType.BREATHING_RATE,
    MetricType.SPO2,
    MetricType.SKIN_TEMPERATURE,
]


class AffectPipeline:
    """Orchestrator for the affect inference subsystem.

    Parameters
    ----------
    reading_repo : ReadingRepository
        Access to raw sensor readings.
    inference_repo : InferenceOutputRepository
        Persist inference outputs.
    feature_repo : FeatureWindowRepository
        Persist feature windows.
    baseline_repo : BaselineRepository
        Load and update personalised baselines.
    ema_repo : EMARepository
        Access EMA labels (for daily count, etc.).
    ema_scheduler : EMAScheduler
        Manage EMA prompt logic.
    window_seconds : int
        Feature window duration in seconds (default 300 = 5 min).
    """

    def __init__(
        self,
        reading_repo: ReadingRepository,
        inference_repo: InferenceOutputRepository,
        feature_repo: FeatureWindowRepository,
        baseline_repo: BaselineRepository,
        ema_repo: EMARepository,
        ema_scheduler: EMAScheduler | None = None,
        window_seconds: int = 300,
    ) -> None:
        self._reading_repo = reading_repo
        self._inference_repo = inference_repo
        self._feature_repo = feature_repo
        self._baseline_repo = baseline_repo
        self._ema_repo = ema_repo
        self._ema_scheduler = ema_scheduler or EMAScheduler()
        self._window_seconds = window_seconds

    async def run_inference(
        self,
        participant_id: str,
        *,
        window_end: datetime | None = None,
        last_sync_time: datetime | None = None,
    ) -> InferenceOutput:
        """Run the full affect inference pipeline for a participant.

        Steps
        -----
        1. Determine time window
        2. Fetch recent readings (daytime + overnight)
        3. Load personalised baseline
        4. Build feature window
        5. Run inference
        6. Update baseline via EWMA
        7. Persist feature window + inference output
        8. Check EMA trigger

        Returns the :class:`InferenceOutput`.
        """
        now = window_end or datetime.utcnow()
        window_start = now - timedelta(seconds=self._window_seconds)

        # 1. Fetch daytime readings in window
        daytime_metrics = [
            MetricType.HEART_RATE,
            MetricType.STEPS,
            MetricType.CALORIES,
            MetricType.ACTIVE_ZONE_MINUTES,
        ]
        all_readings = []
        for metric in daytime_metrics:
            rows = await self._reading_repo.get_range(
                participant_id, metric, window_start, now
            )
            all_readings.extend(rows)

        # 2. Fetch overnight metrics (most recent, typically from last night)
        overnight_start = now - timedelta(hours=24)
        overnight: dict[MetricType, Any] = {}
        for metric in _OVERNIGHT_METRICS:
            rows = await self._reading_repo.get_latest(participant_id, metric, limit=1)
            if rows:
                overnight[metric] = rows

        # 3. Fetch sleep data
        sleep_rows = await self._reading_repo.get_latest(
            participant_id, MetricType.SLEEP, limit=1
        )

        # 4. Load baseline
        baseline_row = await self._baseline_repo.get(participant_id)
        baseline: ParticipantBaseline | None = None
        if baseline_row:
            baseline = ParticipantBaseline(
                participant_id=baseline_row.participant_id,
                updated_at=baseline_row.updated_at,
                hr_baseline_morning=baseline_row.hr_baseline_morning,
                hr_baseline_afternoon=baseline_row.hr_baseline_afternoon,
                hr_baseline_evening=baseline_row.hr_baseline_evening,
                hr_baseline_night=baseline_row.hr_baseline_night,
                hr_baseline_rest=baseline_row.hr_baseline_rest,
                hr_std_baseline=baseline_row.hr_std_baseline,
                hrv_rmssd_baseline=baseline_row.hrv_rmssd_baseline,
                hrv_rmssd_std=baseline_row.hrv_rmssd_std,
                br_baseline=baseline_row.br_baseline,
                br_std=baseline_row.br_std,
                skin_temp_baseline=baseline_row.skin_temp_baseline,
                sleep_duration_baseline=baseline_row.sleep_duration_baseline,
                sleep_efficiency_baseline=baseline_row.sleep_efficiency_baseline,
                ewma_alpha=baseline_row.ewma_alpha,
                observation_count=baseline_row.observation_count,
            )

        # 5. Build feature window
        feature_window = extract_feature_window(
            participant_id=participant_id,
            readings=all_readings,
            window_start=window_start,
            window_end=now,
            baseline=baseline,
            sleep_readings=list(sleep_rows),
            overnight_readings=overnight,
            last_sync_time=last_sync_time,
        )

        # 6. Run inference
        output = infer_affective_state(feature_window)

        # 7. Update baseline
        if baseline is None:
            baseline = ParticipantBaseline(participant_id=participant_id)
        baseline = update_baseline_ewma(baseline, feature_window)
        await self._baseline_repo.upsert(baseline)

        # 8. Persist
        await self._feature_repo.save(feature_window)
        await self._inference_repo.save(output)

        # 9. Check EMA trigger
        daily_count = await self._ema_repo.count_today(participant_id)
        ema_result = self._ema_scheduler.should_trigger_event_prompt(
            participant_id, output, daily_ema_count=daily_count
        )
        if ema_result.get("trigger"):
            logger.info(
                "affect.ema_prompt_triggered",
                participant=participant_id,
                reason=ema_result.get("reason"),
            )
            # The API layer / notification system handles actual delivery

        return output

    async def get_latest_state(
        self, participant_id: str
    ) -> InferenceOutput | None:
        """Return the most recent inference output for a participant."""
        rows = await self._inference_repo.get_latest(participant_id, limit=1)
        if not rows:
            return None
        return self._row_to_output(rows[0])

    async def get_history(
        self,
        participant_id: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """Return inference history as serialisable dicts."""
        rows = await self._inference_repo.get_range(participant_id, start, end)
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "arousal_score": r.arousal_score,
                "arousal_confidence": r.arousal_confidence,
                "stress_score": r.stress_score,
                "stress_confidence": r.stress_confidence,
                "valence_score": r.valence_score,
                "valence_confidence": r.valence_confidence,
                "dominant_emotion": r.dominant_emotion,
                "activity_context": r.activity_context,
                "explanation": r.explanation,
                "model_version": r.model_version,
            }
            for r in rows
        ]

    @staticmethod
    def _row_to_output(row: Any) -> InferenceOutput:
        """Convert a DB row to an InferenceOutput model."""
        import json

        from wearable_agent.affect.models import (
            ActivityContext,
            AffectiveState,
            ArousalLevel,
            Confidence,
            DiscreteEmotion,
            QualityFlags,
            StressLevel,
            ValenceLevel,
        )

        state = AffectiveState(
            arousal_score=row.arousal_score,
            arousal_level=ArousalLevel.MODERATE,  # re-derive from score
            arousal_confidence=Confidence(row.arousal_confidence),
            stress_score=row.stress_score,
            stress_level=StressLevel.MODERATE_STRESS,
            stress_confidence=Confidence(row.stress_confidence),
            valence_score=row.valence_score,
            valence_level=ValenceLevel.NEUTRAL,
            valence_confidence=Confidence(row.valence_confidence),
            dominant_emotion=DiscreteEmotion(row.dominant_emotion),
            dominant_emotion_confidence=Confidence(row.dominant_emotion_confidence),
        )

        return InferenceOutput(
            id=row.id,
            participant_id=row.participant_id,
            timestamp=row.timestamp,
            state=state,
            feature_window_id=row.feature_window_id,
            activity_context=ActivityContext(row.activity_context),
            contributing_signals=json.loads(row.contributing_signals_json),
            explanation=row.explanation,
            top_features=json.loads(row.top_features_json),
            quality=QualityFlags.model_validate_json(row.quality_json),
            model_version=row.model_version,
        )
