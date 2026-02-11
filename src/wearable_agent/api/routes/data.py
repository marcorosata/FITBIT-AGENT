"""Data ingestion and query routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from wearable_agent.api.schemas import IngestRequest
from wearable_agent.models import MetricType, SensorReading
from wearable_agent.storage.repository import AlertRepository, ReadingRepository

router = APIRouter(tags=["data"])


@router.post("/ingest", status_code=201)
async def ingest(req: IngestRequest):
    """Ingest a single sensor reading into the pipeline."""
    from wearable_agent.api.server import _pipeline

    if _pipeline is None:
        raise HTTPException(503, "Pipeline not ready.")
    reading = SensorReading(
        participant_id=req.participant_id,
        device_type=req.device_type,
        metric_type=req.metric_type,
        value=req.value,
        unit=req.unit,
        timestamp=req.timestamp or datetime.utcnow(),
        metadata=req.metadata,
    )
    await _pipeline.publish(reading)
    return {"id": reading.id, "queued": True}


@router.post("/ingest/batch", status_code=201)
async def ingest_batch(readings: list[IngestRequest]):
    """Ingest multiple readings at once."""
    from wearable_agent.api.server import _pipeline

    if _pipeline is None:
        raise HTTPException(503, "Pipeline not ready.")
    objs = [
        SensorReading(
            participant_id=r.participant_id,
            device_type=r.device_type,
            metric_type=r.metric_type,
            value=r.value,
            unit=r.unit,
            timestamp=r.timestamp or datetime.utcnow(),
            metadata=r.metadata,
        )
        for r in readings
    ]
    await _pipeline.publish_batch(objs)
    return {"count": len(objs), "queued": True}


@router.get("/readings/{participant_id}")
async def get_readings(
    participant_id: str,
    metric: MetricType = Query(...),
    limit: int = Query(50, ge=1, le=1000),
):
    repo = ReadingRepository()
    rows = await repo.get_latest(participant_id, metric, limit=limit)
    return [
        {
            "id": r.id,
            "value": r.value,
            "unit": r.unit,
            "timestamp": r.timestamp.isoformat(),
            "device_type": r.device_type,
        }
        for r in rows
    ]


@router.get("/alerts/{participant_id}")
async def get_alerts(participant_id: str, limit: int = Query(50, ge=1, le=500)):
    repo = AlertRepository()
    rows = await repo.get_by_participant(participant_id, limit=limit)
    return [
        {
            "id": r.id,
            "severity": r.severity,
            "metric": r.metric_type,
            "message": r.message,
            "value": r.value,
            "timestamp": r.timestamp.isoformat(),
        }
        for r in rows
    ]
