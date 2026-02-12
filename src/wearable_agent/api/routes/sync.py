"""Fitbit data sync API routes — trigger and monitor data collection."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from wearable_agent.collectors.fitbit import FitbitCollector
from wearable_agent.models import MetricType
from wearable_agent.storage.repository import ParticipantRepository, TokenRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])

# Module-level reference — set by server lifespan
_scheduler_service: Any = None
_pipeline: Any = None


def set_scheduler(scheduler: Any, pipeline: Any = None) -> None:
    """Wire the scheduler service into this router at startup."""
    global _scheduler_service, _pipeline
    _scheduler_service = scheduler
    _pipeline = pipeline


class SyncRequest(BaseModel):
    metrics: list[str] | None = None
    date: str | None = None  # YYYY-MM-DD, defaults to today


class LiveStreamRequest(BaseModel):
    """Request body for starting a live Fitbit data stream."""
    metrics: list[str] | None = None
    date: str | None = None  # YYYY-MM-DD, defaults to today
    continuous: bool = False  # If True, keep syncing periodically


# ── Sync endpoints ────────────────────────────────────────────


@router.post("/{participant_id}", summary="Trigger sync for participant")
async def sync_participant(participant_id: str, req: SyncRequest | None = None):
    """Trigger an immediate data sync for a single participant.

    Uses the stored OAuth tokens to fetch data from Fitbit.
    """
    if _scheduler_service is not None:
        result = await _scheduler_service.trigger_sync(participant_id)
        return result

    # Fallback if scheduler not available — direct sync
    return await _direct_sync(participant_id, req)


@router.post("", summary="Trigger sync for all participants")
async def sync_all():
    """Trigger an immediate data sync for all active participants."""
    if _scheduler_service is None:
        raise HTTPException(503, "Scheduler service not available.")
    result = await _scheduler_service.trigger_sync_all()
    return result


@router.get("/status", summary="Get scheduler status")
async def scheduler_status():
    """Return current scheduler status and statistics."""
    if _scheduler_service is None:
        return {"enabled": False, "status": "not_running"}
    return {
        "enabled": True,
        "running": _scheduler_service.is_running,
        "stats": _scheduler_service.stats,
    }


@router.get("/devices/{participant_id}", summary="List participant's Fitbit devices")
async def get_devices(participant_id: str):
    """List all Fitbit devices linked to a participant's account."""
    token_repo = TokenRepository()
    token_row = await token_repo.get(participant_id, "fitbit")
    if token_row is None:
        raise HTTPException(404, "No Fitbit tokens found for this participant.")

    collector = FitbitCollector()
    try:
        await collector.authenticate(
            access_token=token_row.access_token,
            refresh_token=token_row.refresh_token,
        )
        devices = await collector.get_devices()
    except Exception as exc:
        raise HTTPException(502, f"Failed to fetch devices: {exc}")
    finally:
        await collector.close()

    return {"participant_id": participant_id, "devices": devices}


# ── Direct sync fallback ─────────────────────────────────────


async def _direct_sync(participant_id: str, req: SyncRequest | None = None) -> dict[str, Any]:
    """Perform a direct sync without the scheduler (for single-participant use)."""
    token_repo = TokenRepository()
    token_row = await token_repo.get(participant_id, "fitbit")
    if token_row is None:
        raise HTTPException(404, "No Fitbit tokens found. Link Fitbit first via /auth/fitbit.")

    metrics = [MetricType.HEART_RATE, MetricType.STEPS, MetricType.SLEEP]
    if req and req.metrics:
        metrics = []
        for m in req.metrics:
            try:
                metrics.append(MetricType(m))
            except ValueError:
                raise HTTPException(400, f"Invalid metric: {m}")

    collector = FitbitCollector()
    try:
        await collector.authenticate(
            access_token=token_row.access_token,
            refresh_token=token_row.refresh_token,
        )
        readings = await collector.fetch(
            participant_id, metrics, date=req.date if req else None
        )
    except Exception as exc:
        raise HTTPException(502, f"Fitbit sync failed: {exc}")
    finally:
        await collector.close()

    # Publish to pipeline if available
    if _pipeline is not None and readings:
        await _pipeline.publish_batch(readings)

    logger.info("sync.direct", participant=participant_id, readings=len(readings))
    return {
        "participant_id": participant_id,
        "readings": len(readings),
        "metrics": [m.value for m in metrics],
    }


# ── Live Fitbit streaming ────────────────────────────────────

@router.post("/stream/{participant_id}", summary="Start live Fitbit data stream")
async def start_live_stream(
    participant_id: str,
    req: LiveStreamRequest | None = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Start streaming live Fitbit data for a participant.

    Fetches current data from the Fitbit API using stored OAuth tokens
    and pushes it through the pipeline → WebSocket to connected clients.
    This is the 'live' counterpart of the LifeSnaps dataset replay.
    """
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline service not available")

    # Verify tokens exist
    token_repo = TokenRepository()
    token_row = await token_repo.get(participant_id, "fitbit")
    if token_row is None:
        raise HTTPException(
            status_code=404,
            detail="No Fitbit tokens found. Link Fitbit first via /auth/fitbit.",
        )

    logger.info("sync.live_stream_scheduled", participant=participant_id)
    background_tasks.add_task(
        _run_live_stream,
        participant_id,
        req.metrics if req and req.metrics else None,
        req.date if req else None,
        req.continuous if req else False,
    )

    return {
        "status": "live_stream_started",
        "participant_id": participant_id,
        "source": "live_fitbit",
    }


async def _run_live_stream(
    participant_id: str,
    metric_names: list[str] | None,
    date: str | None,
    continuous: bool,
) -> None:
    """Background task: fetch live Fitbit data and push to the pipeline."""
    import asyncio as _aio

    metrics = [
        MetricType.HEART_RATE,
        MetricType.STEPS,
        MetricType.CALORIES,
        MetricType.DISTANCE,
        MetricType.SPO2,
        MetricType.HRV,
        MetricType.BREATHING_RATE,
        MetricType.SLEEP,
        MetricType.SKIN_TEMPERATURE,
    ]
    if metric_names:
        metrics = []
        for m in metric_names:
            try:
                metrics.append(MetricType(m))
            except ValueError:
                logger.warning("sync.live_stream_bad_metric", metric=m)

    token_repo = TokenRepository()
    total_readings = 0
    rounds = 0

    try:
        while True:
            rounds += 1
            token_row = await token_repo.get(participant_id, "fitbit")
            if token_row is None:
                logger.error("sync.live_stream_no_token", participant=participant_id)
                break

            collector = FitbitCollector()
            try:
                await collector.authenticate(
                    access_token=token_row.access_token,
                    refresh_token=token_row.refresh_token,
                )
                readings = await collector.fetch(participant_id, metrics, date=date)
            except Exception as exc:
                logger.error(
                    "sync.live_stream_fetch_error",
                    participant=participant_id,
                    error=str(exc),
                    exc_info=True,
                )
                break
            finally:
                await collector.close()

            if _pipeline is not None and readings:
                # Tag readings as 'live' source
                for r in readings:
                    if r.metadata is None:
                        r.metadata = {}
                    r.metadata["source"] = "live"
                await _pipeline.publish_batch(readings)
            total_readings += len(readings)

            logger.info(
                "sync.live_stream_round",
                participant=participant_id,
                round=rounds,
                readings=len(readings),
                total=total_readings,
            )

            if not continuous:
                break

            # Wait before next round (5 minutes)
            await _aio.sleep(300)

    except Exception as e:
        logger.error(
            "sync.live_stream_error",
            participant=participant_id,
            error=str(e),
            exc_info=True,
        )
    finally:
        logger.info(
            "sync.live_stream_finished",
            participant=participant_id,
            total_readings=total_readings,
            rounds=rounds,
        )
