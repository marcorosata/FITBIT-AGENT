"""EMA (Ecological Momentary Assessment) — prompt scheduling and management.

Implements the EMA protocol recommended in the specification:
- 4–8 scheduled prompts per day (configurable)
- Event-based prompts when stress_score exceeds threshold at rest
- User-initiated prompts via API

EMA labels serve as ground truth for:
- Model calibration (Platt scaling / isotonic regression)
- Intra-subject personalisation
- Validation metrics (AUROC, F1, Brier score)
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

import structlog

from wearable_agent.affect.models import (
    Confidence,
    DiscreteEmotion,
    EMALabel,
    InferenceOutput,
)

logger = structlog.get_logger(__name__)

# ── Configuration ─────────────────────────────────────────────

# Default prompt schedule: times of day for scheduled EMA prompts
# Spread across waking hours (08:00 – 22:00) for 6 daily prompts
DEFAULT_PROMPT_TIMES = [
    time(8, 30),
    time(10, 30),
    time(12, 30),
    time(14, 30),
    time(17, 30),
    time(20, 30),
]

# Stress threshold for event-based EMA triggers
STRESS_TRIGGER_THRESHOLD = 0.65

# Minimum interval between event-based prompts (avoid "prompt fatigue")
MIN_EVENT_PROMPT_INTERVAL = timedelta(hours=2)

# Maximum EMA prompts per day (scheduled + event-based)
MAX_DAILY_PROMPTS = 8


# ── EMA scheduler ────────────────────────────────────────────


class EMAScheduler:
    """Manages EMA prompt scheduling and event-based triggering.

    Parameters
    ----------
    prompt_times : list[time]
        Times of day for scheduled prompts.
    max_daily : int
        Maximum total prompts per day (scheduled + event-based).
    stress_threshold : float
        Stress score threshold for event-based triggers.
    min_event_interval : timedelta
        Minimum interval between event-based prompts.
    """

    def __init__(
        self,
        prompt_times: list[time] | None = None,
        max_daily: int = MAX_DAILY_PROMPTS,
        stress_threshold: float = STRESS_TRIGGER_THRESHOLD,
        min_event_interval: timedelta = MIN_EVENT_PROMPT_INTERVAL,
    ) -> None:
        self._prompt_times = prompt_times or DEFAULT_PROMPT_TIMES
        self._max_daily = max_daily
        self._stress_threshold = stress_threshold
        self._min_event_interval = min_event_interval

        # Track last event-based prompt timestamp per participant
        self._last_event_prompt: dict[str, datetime] = {}
        # Track daily prompt count per participant
        self._daily_counts: dict[str, int] = {}
        self._daily_date: dict[str, str] = {}

    # ── Scheduled prompts ────────────────────────────────────

    def get_scheduled_prompts(
        self,
        current_time: datetime | None = None,
    ) -> list[time]:
        """Return all scheduled prompt times for today.

        In production, a scheduler service calls this at startup and
        creates cron/timer entries for each time.
        """
        return list(self._prompt_times)

    def is_prompt_due(
        self,
        current_time: datetime | None = None,
        tolerance_minutes: int = 5,
    ) -> bool:
        """Check if a scheduled prompt is due within tolerance."""
        now = current_time or datetime.utcnow()
        now_time = now.time()
        for pt in self._prompt_times:
            dt_prompt = datetime.combine(now.date(), pt)
            diff = abs((now - dt_prompt).total_seconds())
            if diff <= tolerance_minutes * 60:
                return True
        return False

    # ── Event-based prompts ──────────────────────────────────

    def should_trigger_event_prompt(
        self,
        participant_id: str,
        inference: InferenceOutput,
        daily_ema_count: int = 0,
    ) -> dict[str, Any]:
        """Evaluate whether an event-based EMA prompt should fire.

        Triggers when:
        1. Stress score exceeds threshold
        2. Activity context is rest or low movement (avoid exercise)
        3. Enough time since last event prompt
        4. Daily limit not reached

        Returns
        -------
        dict
            ``{"trigger": True/False, "reason": str, ...}``
        """
        result: dict[str, Any] = {"trigger": False, "reason": ""}

        stress = inference.state.stress_score
        ctx = inference.activity_context.value
        now = inference.timestamp

        # Check daily limit
        today_str = now.strftime("%Y-%m-%d")
        if self._daily_date.get(participant_id) != today_str:
            self._daily_counts[participant_id] = 0
            self._daily_date[participant_id] = today_str
        total_today = daily_ema_count + self._daily_counts.get(participant_id, 0)
        if total_today >= self._max_daily:
            result["reason"] = "daily_limit_reached"
            return result

        # Check stress threshold
        if stress < self._stress_threshold:
            result["reason"] = "stress_below_threshold"
            return result

        # Check activity context (avoid prompting during exercise)
        if ctx in ("high_movement", "moderate_movement"):
            result["reason"] = "physical_activity_in_progress"
            return result

        # Check minimum interval
        last = self._last_event_prompt.get(participant_id)
        if last is not None:
            elapsed = (now - last).total_seconds()
            if elapsed < self._min_event_interval.total_seconds():
                result["reason"] = f"too_recent (last {int(elapsed)}s ago)"
                return result

        # Trigger!
        self._last_event_prompt[participant_id] = now
        self._daily_counts[participant_id] = self._daily_counts.get(participant_id, 0) + 1

        result["trigger"] = True
        result["reason"] = f"stress_score={stress:.2f} at {ctx}"
        result["inference_output_id"] = inference.id
        result["stress_score"] = stress

        logger.info(
            "ema.event_triggered",
            participant=participant_id,
            stress=round(stress, 2),
            context=ctx,
        )
        return result


# ── EMA label factory ────────────────────────────────────────


def create_ema_label(
    participant_id: str,
    arousal: int | None = None,
    valence: int | None = None,
    stress: int | None = None,
    emotion_tag: str | None = None,
    context_note: str = "",
    trigger: str = "scheduled",
    inference_output_id: str | None = None,
) -> EMALabel:
    """Create and validate an EMA label from user input.

    Parameters
    ----------
    arousal : int | None
        Self-rated arousal (1-9 SAM scale).
    valence : int | None
        Self-rated valence (1-9 SAM scale).
    stress : int | None
        Self-rated stress (1-5 scale).
    emotion_tag : str | None
        Discrete emotion label string (must match DiscreteEmotion enum).
    context_note : str
        Free-text context from the participant.
    trigger : str
        What triggered this EMA: 'scheduled', 'event_based', 'user_initiated'.
    inference_output_id : str | None
        ID of the inference output that triggered this EMA (if event-based).
    """
    parsed_emotion: DiscreteEmotion | None = None
    if emotion_tag:
        try:
            parsed_emotion = DiscreteEmotion(emotion_tag.lower())
        except ValueError:
            logger.warning("ema.invalid_emotion_tag", tag=emotion_tag)
            parsed_emotion = None

    return EMALabel(
        participant_id=participant_id,
        arousal=arousal,
        valence=valence,
        stress=stress,
        emotion_tag=parsed_emotion,
        context_note=context_note,
        trigger=trigger,
        inference_output_id=inference_output_id,
    )
