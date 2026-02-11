"""Affect inference and EMA routes."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from wearable_agent.affect.ema import create_ema_label
from wearable_agent.api.schemas import AffectRequest, EMARequest
from wearable_agent.storage.repository import EMARepository

router = APIRouter(tags=["affect"])


@router.post("/affect/{participant_id}")
async def run_affect_inference(participant_id: str, req: AffectRequest | None = None):
    """Run affective state inference for a participant.

    Computes arousal, stress, valence, and discrete emotion estimates
    from the most recent feature window.  Results include confidence
    levels and explainability fields.
    """
    from wearable_agent.api.server import _affect_pipeline

    if _affect_pipeline is None:
        raise HTTPException(503, "Affect pipeline not ready.")

    output = await _affect_pipeline.run_inference(participant_id)
    return output.model_dump(mode="json")


@router.get("/affect/{participant_id}")
async def get_affect_state(participant_id: str):
    """Get the latest affective state for a participant."""
    from wearable_agent.api.server import _affect_pipeline

    if _affect_pipeline is None:
        raise HTTPException(503, "Affect pipeline not ready.")

    output = await _affect_pipeline.get_latest_state(participant_id)
    if output is None:
        raise HTTPException(404, "No affect inference found. Run POST /affect/{id} first.")
    return output.model_dump(mode="json")


@router.get("/affect/{participant_id}/history")
async def get_affect_history(
    participant_id: str,
    hours: int = Query(24, ge=1, le=720),
):
    """Get affect inference history for a participant."""
    from wearable_agent.api.server import _affect_pipeline

    if _affect_pipeline is None:
        raise HTTPException(503, "Affect pipeline not ready.")

    end = datetime.utcnow()
    start = end - timedelta(hours=hours)
    history = await _affect_pipeline.get_history(participant_id, start, end)
    return {"participant_id": participant_id, "count": len(history), "history": history}


@router.post("/ema", status_code=201)
async def submit_ema(req: EMARequest):
    """Submit an EMA (Ecological Momentary Assessment) self-report.

    EMA labels serve as ground truth for affect inference calibration.
    Supports SAM scales (arousal 1-9, valence 1-9), stress (1-5),
    and discrete emotion tagging.
    """
    label = create_ema_label(
        participant_id=req.participant_id,
        arousal=req.arousal,
        valence=req.valence,
        stress=req.stress,
        emotion_tag=req.emotion_tag,
        context_note=req.context_note,
        trigger=req.trigger,
        inference_output_id=req.inference_output_id,
    )
    ema_repo = EMARepository()
    await ema_repo.save(label)
    return {"id": label.id, "saved": True}


@router.get("/ema/{participant_id}")
async def get_ema_labels(
    participant_id: str,
    limit: int = Query(50, ge=1, le=500),
):
    """Get EMA labels for a participant."""
    repo = EMARepository()
    rows = await repo.get_by_participant(participant_id, limit=limit)
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat(),
            "arousal": r.arousal,
            "valence": r.valence,
            "stress": r.stress,
            "emotion_tag": r.emotion_tag,
            "context_note": r.context_note,
            "trigger": r.trigger,
        }
        for r in rows
    ]
