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
        logger.error("lifesnaps.list_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load dataset: {e}")


@router.get("/debug", summary="Debug data file locations")
def debug_data_files():
    """Show data file paths and sizes for debugging deployment issues."""
    import os
    from wearable_agent.config import _PROJECT_ROOT

    result: dict[str, object] = {
        "project_root": str(_PROJECT_ROOT),
        "cwd": os.getcwd(),
        "build_version": "v4-participant-bson",  # bump this to confirm deploy
    }

    candidates = [
        _PROJECT_ROOT / "scripts" / "rais_anonymized",
        _PROJECT_ROOT / "data" / "lifesnaps" / "rais_anonymized",
    ]
    for p in candidates:
        key = str(p.relative_to(_PROJECT_ROOT))
        csv_dir = p / "csv_rais_anonymized"
        daily = csv_dir / "daily_fitbit_sema_df_unprocessed.csv"
        hourly = csv_dir / "hourly_fitbit_sema_df_unprocessed.csv"
        mongo = p / "mongo_rais_anonymized"
        result[key] = {
            "exists": p.exists(),
            "daily_csv_exists": daily.exists(),
            "daily_csv_size_bytes": daily.stat().st_size if daily.exists() else 0,
            "hourly_csv_exists": hourly.exists(),
            "hourly_csv_size_bytes": hourly.stat().st_size if hourly.exists() else 0,
            "mongo_dir_exists": mongo.exists(),
            "mongo_files": (
                [
                    {"name": f.name, "size_mb": round(f.stat().st_size / 1024 / 1024, 1)}
                    for f in mongo.iterdir()
                    if f.is_file()
                ]
                + [{"name": d.name, "type": "dir"} for d in mongo.iterdir() if d.is_dir()]
                if mongo.exists()
                else []
            ),
        }

    # Check if LFS pointers (small files ~130 bytes)
    for p in candidates:
        daily = p / "csv_rais_anonymized" / "daily_fitbit_sema_df_unprocessed.csv"
        if daily.exists() and daily.stat().st_size < 200:
            key = str(p.relative_to(_PROJECT_ROOT))
            result[f"{key}_WARNING"] = "CSV file is too small — likely an LFS pointer, not real data"

    return result


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
        MetricType.DISTANCE,
        MetricType.VO2_MAX,
        MetricType.SKIN_TEMPERATURE,
        MetricType.RESTING_HEART_RATE,
        MetricType.SLEEP_EFFICIENCY,
        MetricType.AFFECT_TAG
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
