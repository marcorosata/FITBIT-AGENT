"""FastAPI application — REST endpoints and WebSocket for real-time data."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from wearable_agent.agent.core import WearableAgent
from wearable_agent.config import get_settings
from wearable_agent.models import (
    Alert,
    AlertSeverity,
    DeviceType,
    MetricType,
    MonitoringRule,
    SensorReading,
)
from wearable_agent.monitors.heart_rate import create_heart_rate_engine
from wearable_agent.monitors.rules import RuleEngine
from wearable_agent.notifications.handlers import create_dispatcher
from wearable_agent.storage.database import (
    AlertRow,
    SensorReadingRow,
    get_session,
    get_session_factory,
    init_db,
)
from wearable_agent.storage.repository import (
    AlertRepository,
    BaselineRepository,
    EMARepository,
    FeatureWindowRepository,
    InferenceOutputRepository,
    ReadingRepository,
)
from wearable_agent.streaming.pipeline import StreamPipeline
from wearable_agent.affect.ema import EMAScheduler, create_ema_label
from wearable_agent.affect.pipeline import AffectPipeline

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"

logger = structlog.get_logger(__name__)

# ── Shared state (initialised in lifespan) ────────────────────

_pipeline: StreamPipeline | None = None
_agent: WearableAgent | None = None
_rule_engine: RuleEngine | None = None
_pipeline_task: asyncio.Task | None = None
_affect_pipeline: AffectPipeline | None = None
_ema_scheduler: EMAScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hooks."""
    global _pipeline, _agent, _rule_engine, _pipeline_task
    global _affect_pipeline, _ema_scheduler

    settings = get_settings()

    # 1. Database
    await init_db()
    logger.info("server.db_ready")

    # 2. Monitoring engine
    _rule_engine = create_heart_rate_engine()

    # 3. Notifications
    dispatcher = create_dispatcher(settings)

    # 4. Repositories
    reading_repo = ReadingRepository()
    alert_repo = AlertRepository()
    inference_repo = InferenceOutputRepository()
    feature_repo = FeatureWindowRepository()
    baseline_repo = BaselineRepository()
    ema_repo = EMARepository()

    # 5. Affect inference pipeline
    _ema_scheduler = EMAScheduler()
    _affect_pipeline = AffectPipeline(
        reading_repo=reading_repo,
        inference_repo=inference_repo,
        feature_repo=feature_repo,
        baseline_repo=baseline_repo,
        ema_repo=ema_repo,
        ema_scheduler=_ema_scheduler,
    )

    # 6. Agent
    _agent = WearableAgent(
        rule_engine=_rule_engine,
        dispatcher=dispatcher,
        reading_repo=reading_repo,
        alert_repo=alert_repo,
        affect_pipeline=_affect_pipeline,
    )

    # 7. Streaming pipeline
    _pipeline = StreamPipeline()

    async def _on_reading(reading: SensorReading) -> None:
        """Pipeline consumer: persist + evaluate."""
        await reading_repo.save(reading)
        await _agent.process_reading(reading)  # type: ignore[union-attr]

    _pipeline.add_consumer(_on_reading)
    _pipeline_task = asyncio.create_task(_pipeline.start())
    logger.info("server.started", port=settings.api_port)

    yield  # ← application runs

    # Shutdown
    if _pipeline:
        await _pipeline.stop()
    if _pipeline_task:
        _pipeline_task.cancel()
    logger.info("server.stopped")


app = FastAPI(
    title="Wearable Agent API",
    description="Agent-based framework for wearable data collection and analysis in research.",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Request / response models ────────────────────────────────

class IngestRequest(BaseModel):
    participant_id: str
    device_type: DeviceType
    metric_type: MetricType
    value: float
    unit: str = ""
    timestamp: datetime | None = None
    metadata: dict[str, Any] = {}


class AnalyseRequest(BaseModel):
    query: str


class RuleRequest(BaseModel):
    metric_type: MetricType
    condition: str
    severity: AlertSeverity = AlertSeverity.WARNING
    message_template: str = "Metric {metric_type} value {value} breached rule."


# ── Health ────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "pipeline_pending": _pipeline.pending if _pipeline else 0}


# ── Data ingestion ────────────────────────────────────────────

@app.post("/ingest", status_code=201)
async def ingest(req: IngestRequest):
    """Ingest a single sensor reading into the pipeline."""
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


@app.post("/ingest/batch", status_code=201)
async def ingest_batch(readings: list[IngestRequest]):
    """Ingest multiple readings at once."""
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


# ── Query ─────────────────────────────────────────────────────

@app.get("/readings/{participant_id}")
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


@app.get("/alerts/{participant_id}")
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


# ── Agent analysis ────────────────────────────────────────────

@app.post("/analyse")
async def analyse(req: AnalyseRequest):
    """Send a free-form question to the LLM agent."""
    if _agent is None:
        raise HTTPException(503, "Agent not ready.")
    result = await _agent.analyse(req.query)
    return {"response": result}


@app.get("/evaluate/{participant_id}")
async def evaluate_participant(
    participant_id: str,
    metric: str = Query("heart_rate"),
    hours: int = Query(24, ge=1, le=168),
):
    """Ask the agent for a structured evaluation of a participant."""
    if _agent is None:
        raise HTTPException(503, "Agent not ready.")
    result = await _agent.evaluate_participant(participant_id, metric, hours)
    return {"evaluation": result}


# ── Monitoring rules ──────────────────────────────────────────

@app.get("/rules")
async def list_rules():
    if _rule_engine is None:
        return []
    return [r.model_dump() for r in _rule_engine.list_rules()]


@app.post("/rules", status_code=201)
async def add_rule(req: RuleRequest):
    if _rule_engine is None:
        raise HTTPException(503, "Rule engine not ready.")
    rule = MonitoringRule(
        metric_type=req.metric_type,
        condition=req.condition,
        severity=req.severity,
        message_template=req.message_template,
    )
    _rule_engine.add_rule(rule)
    return {"rule_id": rule.rule_id}


@app.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    if _rule_engine is None:
        raise HTTPException(503, "Rule engine not ready.")
    removed = _rule_engine.remove_rule(rule_id)
    if not removed:
        raise HTTPException(404, "Rule not found.")
    return {"removed": True}


# ── Affect inference ──────────────────────────────────────────


class AffectRequest(BaseModel):
    """Trigger affect inference for a participant."""
    window_seconds: int = 300


class EMARequest(BaseModel):
    """Submit an EMA self-report label."""
    participant_id: str
    arousal: int | None = None       # 1-9 SAM
    valence: int | None = None       # 1-9 SAM
    stress: int | None = None        # 1-5
    emotion_tag: str | None = None   # DiscreteEmotion value
    context_note: str = ""
    trigger: str = "user_initiated"
    inference_output_id: str | None = None


@app.post("/affect/{participant_id}")
async def run_affect_inference(participant_id: str, req: AffectRequest | None = None):
    """Run affective state inference for a participant.

    Computes arousal, stress, valence, and discrete emotion estimates
    from the most recent feature window.  Results include confidence
    levels and explainability fields.
    """
    if _affect_pipeline is None:
        raise HTTPException(503, "Affect pipeline not ready.")

    output = await _affect_pipeline.run_inference(participant_id)
    return output.model_dump(mode="json")


@app.get("/affect/{participant_id}")
async def get_affect_state(participant_id: str):
    """Get the latest affective state for a participant."""
    if _affect_pipeline is None:
        raise HTTPException(503, "Affect pipeline not ready.")

    output = await _affect_pipeline.get_latest_state(participant_id)
    if output is None:
        raise HTTPException(404, "No affect inference found. Run POST /affect/{id} first.")
    return output.model_dump(mode="json")


@app.get("/affect/{participant_id}/history")
async def get_affect_history(
    participant_id: str,
    hours: int = Query(24, ge=1, le=720),
):
    """Get affect inference history for a participant."""
    if _affect_pipeline is None:
        raise HTTPException(503, "Affect pipeline not ready.")

    end = datetime.utcnow()
    start = end - __import__("datetime").timedelta(hours=hours)
    history = await _affect_pipeline.get_history(participant_id, start, end)
    return {"participant_id": participant_id, "count": len(history), "history": history}


@app.post("/ema", status_code=201)
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


@app.get("/ema/{participant_id}")
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


# ── Aggregate stats (for admin dashboard) ─────────────────────

@app.get("/api/stats")
async def get_stats():
    """Return aggregate statistics for the admin dashboard."""
    factory = get_session_factory()
    async with factory() as session:
        # Total readings
        result = await session.execute(select(func.count()).select_from(SensorReadingRow))
        total_readings = result.scalar() or 0

        # Total alerts
        result = await session.execute(select(func.count()).select_from(AlertRow))
        total_alerts = result.scalar() or 0

        # Distinct participants
        result = await session.execute(
            select(SensorReadingRow.participant_id).distinct()
        )
        participants = [row[0] for row in result.all()]

        # Recent alerts (last 20)
        result = await session.execute(
            select(AlertRow).order_by(AlertRow.timestamp.desc()).limit(20)
        )
        recent = result.scalars().all()

    return {
        "total_readings": total_readings,
        "total_alerts": total_alerts,
        "participants": participants,
        "recent_alerts": [
            {
                "id": a.id,
                "participant_id": a.participant_id,
                "severity": a.severity,
                "metric": a.metric_type,
                "message": a.message,
                "value": a.value,
                "timestamp": a.timestamp.isoformat(),
            }
            for a in recent
        ],
    }


# ── UI routes ─────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_ui():
    """Serve the admin dashboard."""
    return FileResponse(_UI_DIR / "admin" / "index.html")


@app.get("/app", response_class=HTMLResponse)
async def user_ui():
    """Serve the participant app."""
    return FileResponse(_UI_DIR / "user" / "index.html")


# ── WebSocket (real-time data feed) ──────────────────────────

_ws_clients: list[WebSocket] = []


@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    """Real-time WebSocket feed of incoming sensor readings."""
    await ws.accept()
    _ws_clients.append(ws)
    logger.info("ws.client_connected", total=len(_ws_clients))
    try:
        while True:
            # Keep connection alive; clients are read-only consumers.
            await ws.receive_text()
    except WebSocketDisconnect:
        _ws_clients.remove(ws)
        logger.info("ws.client_disconnected", total=len(_ws_clients))
