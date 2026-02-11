"""LifeSnaps dataset API routes — manage data replay and streaming."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from wearable_agent.collectors.lifesnaps import LifeSnapsCollector
from wearable_agent.models import MetricType

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/lifesnaps", tags=["lifesnaps"])

_pipeline: Any = None


def set_pipeline(pipeline: Any) -> None:
    """Wire the streaming pipeline into this router at startup."""
    global _pipeline
    _pipeline = pipeline


class StreamRequest(BaseModel):
    speed: float = 1.0  # Real-time multiplier (1.0 = normal, 10.0 = 10x speed)
    metrics: list[MetricType] | None = None


@router.get("/participants", summary="List LifeSnaps participants")
def list_participants():
    """Return a list of all participant IDs available in the dataset."""
    try:
        collector = LifeSnapsCollector()
        return collector.get_participants()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("lifesnaps.list_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to load dataset")


@router.post("/stream/{participant_id}", summary="Start streaming replay")
async def start_streaming(
    participant_id: str,
    req: StreamRequest | None = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Start a background task to replay/stream data for a participant.
    
    Simulates a live device by yielding historical data points with 
    timestamps shifted to the present.
    """
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline service not available")

    speed = req.speed if req else 1.0
    metrics = req.metrics if req and req.metrics else [
        MetricType.HEART_RATE,
        MetricType.STEPS,
        MetricType.STRESS,
        MetricType.SPO2,
        MetricType.HRV,
        MetricType.BREATHING_RATE,
        MetricType.CALORIES,
        MetricType.DISTANCE
    ]

    # Verify participant exists (allow BSON-only participants to pass)
    try:
        collector = LifeSnapsCollector()
        csv_participants = collector.get_participants()
        # Participant may only exist in BSON (MongoDB ObjectID), so don't block
        if participant_id not in csv_participants:
            logger.info("lifesnaps.participant_not_in_csv", participant=participant_id,
                        note="Will attempt BSON stream anyway")
    except FileNotFoundError:
        logger.warning("lifesnaps.csv_not_found", note="Will attempt BSON-only stream")

    logger.info("lifesnaps.stream_scheduled", participant=participant_id, speed=speed)
    background_tasks.add_task(_run_stream, participant_id, metrics, speed)
    
    return {
        "status": "streaming_started", 
        "participant_id": participant_id, 
        "speed": speed,
        "metrics": metrics
    }


async def _run_stream(participant_id: str, metrics: list[MetricType], speed: float):
    """Background task to push readings to the pipeline."""
    collector = LifeSnapsCollector()
    logger.info("lifesnaps.stream_started", participant=participant_id)
    
    count = 0
    try:
        async for reading in collector.stream(participant_id, metrics, speed=speed):
            if _pipeline:
                await _pipeline.publish_batch([reading])
                count += 1
                if count % 100 == 0:
                     logger.debug("lifesnaps.stream_progress", count=count)
    except Exception as e:
        logger.error("lifesnaps.stream_error", error=str(e))
    finally:
        logger.info("lifesnaps.stream_finished", participant=participant_id, total_readings=count)
