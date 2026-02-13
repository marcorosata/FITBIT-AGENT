"""LifeSnaps dataset API routes — manage data replay and streaming."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from wearable_agent.collectors.lifesnaps import LifeSnapsCollector
from wearable_agent.models import MetricType
from wearable_agent.storage.repository import ReadingRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/lifesnaps", tags=["lifesnaps"])

_pipeline: Any = None

# Track active syncs to avoid duplicates
_active_syncs: set[str] = set()


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


# ── Participant data sync (bulk-load into DB) ─────────────────


class SyncResponse(BaseModel):
    status: str
    participant_id: str
    readings_synced: int = 0
    already_synced: bool = False
    message: str = ""


@router.post("/sync/{participant_id}", summary="Sync participant data into DB")
async def sync_participant_data(
    participant_id: str,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    force: bool = False,
):
    """Bulk-load all LifeSnaps data for a participant into the database.

    This is much faster than streaming (no time-shifting delays).
    Use when a participant is selected to ensure their data is queryable.
    Set force=True to re-sync even if data already exists.
    """
    if participant_id in _active_syncs:
        return SyncResponse(
            status="already_running",
            participant_id=participant_id,
            message="Sync already in progress for this participant.",
        )

    reading_repo = ReadingRepository()

    # Check if data already exists
    if not force:
        existing_count = await reading_repo.count_for_participant(participant_id)
        if existing_count > 0:
            logger.info(
                "lifesnaps.sync_skip",
                participant=participant_id,
                existing=existing_count,
            )
            return SyncResponse(
                status="already_synced",
                participant_id=participant_id,
                readings_synced=existing_count,
                already_synced=True,
                message=f"Participant already has {existing_count} readings in DB.",
            )

    # Run sync in background so the request returns immediately
    _active_syncs.add(participant_id)
    background_tasks.add_task(_run_sync, participant_id, force)

    return SyncResponse(
        status="sync_started",
        participant_id=participant_id,
        message="Data sync started in background. Readings will be available shortly.",
    )


@router.get("/sync/{participant_id}/status", summary="Check sync status")
async def sync_status(participant_id: str):
    """Check whether a participant's data has been synced."""
    reading_repo = ReadingRepository()
    count = await reading_repo.count_for_participant(participant_id)
    in_progress = participant_id in _active_syncs
    return {
        "participant_id": participant_id,
        "readings_count": count,
        "synced": count > 0,
        "sync_in_progress": in_progress,
    }


async def _run_sync(participant_id: str, force: bool = False) -> None:
    """Background task: bulk-load participant data from CSV into the DB."""
    reading_repo = ReadingRepository()

    try:
        if force:
            deleted = await reading_repo.delete_for_participant(participant_id)
            logger.info("lifesnaps.sync_cleared", participant=participant_id, deleted=deleted)

        collector = LifeSnapsCollector()

        # Fetch ALL metrics from CSV (fast — no time delay)
        all_metrics = [
            MetricType.HEART_RATE,
            MetricType.STEPS,
            MetricType.STRESS,
            MetricType.SPO2,
            MetricType.HRV,
            MetricType.BREATHING_RATE,
            MetricType.CALORIES,
            MetricType.DISTANCE,
            MetricType.SLEEP,
        ]

        logger.info(
            "lifesnaps.sync_start",
            participant=participant_id,
            metrics=[m.value for m in all_metrics],
        )

        readings = await collector.fetch(participant_id, all_metrics)

        if not readings:
            logger.warning("lifesnaps.sync_no_data", participant=participant_id)
            return

        # Batch insert in chunks to avoid memory issues
        batch_size = 500
        total_saved = 0
        for i in range(0, len(readings), batch_size):
            batch = readings[i : i + batch_size]
            saved = await reading_repo.save_batch(batch)
            total_saved += saved

        logger.info(
            "lifesnaps.sync_complete",
            participant=participant_id,
            total_readings=total_saved,
        )

        # Also push through pipeline if available (triggers monitoring rules + WS broadcast)
        if _pipeline and readings:
            # Push a summary notification through the pipeline
            logger.info(
                "lifesnaps.sync_pipeline_notify",
                participant=participant_id,
                note="Data available for analysis",
            )

    except FileNotFoundError as e:
        logger.error("lifesnaps.sync_file_not_found", participant=participant_id, error=str(e))
    except Exception as e:
        logger.error(
            "lifesnaps.sync_error",
            participant=participant_id,
            error=str(e),
            exc_info=True,
        )
    finally:
        _active_syncs.discard(participant_id)


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
    import time

    collector = LifeSnapsCollector()
    logger.info(
        "lifesnaps.stream_started",
        participant=participant_id,
        speed=speed,
        metrics=[m.value for m in metrics],
        data_path=str(collector.data_path),
    )

    count = 0
    last_log_time = time.monotonic()
    metric_counts: dict[str, int] = {}

    try:
        async for reading in collector.stream(participant_id, metrics, speed=speed):
            if _pipeline:
                await _pipeline.publish_batch([reading])
                count += 1
                metric_counts[reading.metric_type.value] = (
                    metric_counts.get(reading.metric_type.value, 0) + 1
                )

                # Log progress every 30 seconds (wall-clock)
                now = time.monotonic()
                if now - last_log_time >= 30:
                    logger.info(
                        "lifesnaps.stream_progress",
                        participant=participant_id,
                        total=count,
                        per_metric=metric_counts,
                        pipeline_pending=_pipeline.pending,
                    )
                    last_log_time = now
    except Exception as e:
        logger.error(
            "lifesnaps.stream_error",
            participant=participant_id,
            error=str(e),
            readings_so_far=count,
            exc_info=True,
        )
    finally:
        logger.info(
            "lifesnaps.stream_finished",
            participant=participant_id,
            total_readings=count,
            per_metric=metric_counts,
        )
