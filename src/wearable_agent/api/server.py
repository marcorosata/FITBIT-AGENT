"""FastAPI application — app factory, lifespan, and router wiring.

This module creates the FastAPI application and wires together all
infrastructure during the lifespan startup/shutdown cycle.  All route
handlers live in ``wearable_agent.api.routes.*``.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from wearable_agent.agent.core import WearableAgent
from wearable_agent.api.auth import router as auth_router
from wearable_agent.api.middleware import setup_middleware
from wearable_agent.api.routes.admin import router as admin_router
from wearable_agent.api.routes.affect import router as affect_router
from wearable_agent.api.routes.analysis import router as analysis_router
from wearable_agent.api.routes.data import router as data_router
from wearable_agent.api.routes.participants import router as participants_router
from wearable_agent.api.routes.rules import router as rules_router
from wearable_agent.api.routes.sync import router as sync_router, set_scheduler
from wearable_agent.api.routes.lifesnaps import router as lifesnaps_router, set_pipeline as set_lifesnaps_pipeline
from wearable_agent.api.routes.media import router as media_router
from wearable_agent.api.websocket import ws_manager
from wearable_agent.config import get_settings, _PROJECT_ROOT
from wearable_agent.models import SensorReading
from wearable_agent.monitors.heart_rate import create_heart_rate_engine
from wearable_agent.monitors.rules import RuleEngine
from wearable_agent.notifications.handlers import create_dispatcher
from wearable_agent.scheduler.service import SchedulerService
from wearable_agent.storage.database import init_db
from wearable_agent.storage.repository import (
    AlertRepository,
    BaselineRepository,
    EMARepository,
    FeatureWindowRepository,
    InferenceOutputRepository,
    ReadingRepository,
)
from wearable_agent.streaming.pipeline import StreamPipeline
from wearable_agent.affect.ema import EMAScheduler
from wearable_agent.affect.pipeline import AffectPipeline

logger = structlog.get_logger(__name__)

# ── Shared state (initialised in lifespan) ────────────────────

_pipeline: StreamPipeline | None = None
_agent: WearableAgent | None = None
_rule_engine: RuleEngine | None = None
_pipeline_task: asyncio.Task | None = None
_affect_pipeline: AffectPipeline | None = None
_ema_scheduler: EMAScheduler | None = None
_scheduler_service: SchedulerService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hooks."""
    global _pipeline, _agent, _rule_engine, _pipeline_task
    global _affect_pipeline, _ema_scheduler, _scheduler_service

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

    # 7. Streaming pipeline with WebSocket broadcasting
    _pipeline = StreamPipeline()

    async def _on_reading(reading: SensorReading) -> None:
        """Pipeline consumer: persist, evaluate rules, and broadcast."""
        await reading_repo.save(reading)
        alerts = await _agent.process_reading(reading)  # type: ignore[union-attr]

        # Track inbound reading for admin stats
        reading_payload = {
            "id": reading.id,
            "participant_id": reading.participant_id,
            "metric_type": reading.metric_type.value,
            "value": reading.value,
            "unit": reading.unit,
            "timestamp": reading.timestamp.isoformat(),
        }
        ws_manager.record_inbound(reading_payload)

        # Broadcast reading to WebSocket clients
        await ws_manager.broadcast_reading({
            "id": reading.id,
            "participant_id": reading.participant_id,
            "metric_type": reading.metric_type.value,
            "value": reading.value,
            "unit": reading.unit,
            "timestamp": reading.timestamp.isoformat(),
        })

        # Broadcast any fired alerts
        for alert in alerts:
            await ws_manager.broadcast_alert({
                "id": alert.id,
                "participant_id": alert.participant_id,
                "severity": alert.severity.value,
                "metric_type": alert.metric_type.value,
                "message": alert.message,
                "value": alert.value,
                "timestamp": alert.timestamp.isoformat(),
            })

    _pipeline.add_consumer(_on_reading)
    _pipeline_task = asyncio.create_task(_pipeline.start())

    # 7b. Wire LifeSnaps streaming to pipeline
    set_lifesnaps_pipeline(_pipeline)

    # 8. Scheduled data collection
    if settings.scheduler_enabled:
        _scheduler_service = SchedulerService(
            pipeline=_pipeline,
            affect_pipeline=_affect_pipeline,
        )
        set_scheduler(_scheduler_service, _pipeline)
        await _scheduler_service.start()
        logger.info("server.scheduler_started")
    else:
        set_scheduler(None, _pipeline)

    logger.info("server.started", port=settings.api_port)

    # 9. Background: download LFS data files if needed (Railway)
    async def _fetch_lfs_data() -> None:
        """Download LFS pointer files from GitHub in background."""
        import subprocess
        from wearable_agent.config import _PROJECT_ROOT

        script = _PROJECT_ROOT / "scripts" / "fetch_lfs.py"
        if not script.exists():
            return
        try:
            logger.info("server.lfs_fetch_start")
            result = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(_PROJECT_ROOT),
            )
            logger.info("server.lfs_fetch_done", returncode=result.returncode,
                        stdout=result.stdout[-500:] if result.stdout else "")
            if result.stderr:
                logger.warning("server.lfs_fetch_stderr", stderr=result.stderr[-500:])
        except Exception as e:
            logger.error("server.lfs_fetch_error", error=str(e))

    _lfs_task = asyncio.create_task(_fetch_lfs_data())

    yield  # ← application runs

    # Shutdown
    _lfs_task.cancel()
    if _scheduler_service:
        await _scheduler_service.stop()
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

# ── Middleware ────────────────────────────────────────────────
setup_middleware(app)

# ── Static files ─────────────────────────────────────────────
static_dir = _PROJECT_ROOT / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ── Routers ───────────────────────────────────────────────────
app.include_router(admin_router)
app.include_router(data_router)
app.include_router(analysis_router)
app.include_router(rules_router)
app.include_router(affect_router)
app.include_router(auth_router)
app.include_router(participants_router)
app.include_router(sync_router)
app.include_router(lifesnaps_router)
app.include_router(media_router)
