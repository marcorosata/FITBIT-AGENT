"""System health, admin dashboard, UI, and WebSocket routes."""

from __future__ import annotations

import json as _json
from pathlib import Path

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func, select

from wearable_agent.api.websocket import ws_manager
from wearable_agent.config import get_settings
from wearable_agent.storage.database import AlertRow, SensorReadingRow, get_session_factory

_UI_DIR = Path(__file__).resolve().parent.parent.parent / "ui"

logger = structlog.get_logger(__name__)

router = APIRouter()


# ── Health ────────────────────────────────────────────────────

@router.get("/health", tags=["system"])
async def health():
    from wearable_agent.api.server import _pipeline

    return {"status": "ok", "pipeline_pending": _pipeline.pending if _pipeline else 0}


@router.get("/system/info", tags=["system"])
async def system_info():
    """Detailed system status for operational monitoring."""
    from wearable_agent.api.server import (
        _affect_pipeline,
        _agent,
        _pipeline,
        _rule_engine,
        _scheduler_service,
    )

    settings = get_settings()
    return {
        "version": "0.1.0",
        "pipeline": {
            "running": _pipeline is not None,
            "pending": _pipeline.pending if _pipeline else 0,
        },
        "agent": {"ready": _agent is not None},
        "rule_engine": {
            "ready": _rule_engine is not None,
            "rule_count": len(_rule_engine.list_rules()) if _rule_engine else 0,
        },
        "affect_pipeline": {"ready": _affect_pipeline is not None},
        "scheduler": {
            "enabled": settings.scheduler_enabled,
            "running": _scheduler_service is not None and _scheduler_service._running
            if _scheduler_service else False,
            "interval_minutes": settings.scheduler_collect_interval_minutes,
        },
        "websocket": {
            "connected_clients": ws_manager.active_count,
        },
    }


# ── Aggregate stats (for admin dashboard) ─────────────────────

@router.get("/api/stats", tags=["system"])
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


# ── Stream statistics (for admin dashboard) ──────────────────

@router.get("/admin/api/stream-stats", tags=["admin"])
async def stream_stats():
    """Return real-time streaming statistics for the admin UI."""
    return {
        "connections": {
            "total": ws_manager.active_count,
            "channels": ws_manager.channel_breakdown(),
        },
        "throughput": ws_manager.stats.snapshot(),
        "recent_messages": ws_manager.get_recent_messages(limit=100),
    }


@router.get("/admin/api/connections", tags=["admin"])
async def connection_info():
    """Return connected client info per channel."""
    return {
        "total_clients": ws_manager.active_count,
        "channels": ws_manager.channel_breakdown(),
    }


# ── UI routes ────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, tags=["ui"])
async def root_ui():
    """Serve the admin dashboard at the root URL."""
    return FileResponse(_UI_DIR / "admin" / "index.html")


@router.get("/admin", response_class=HTMLResponse, tags=["ui"])
async def admin_ui():
    """Serve the admin dashboard."""
    return FileResponse(_UI_DIR / "admin" / "index.html")


@router.get("/app", response_class=HTMLResponse, tags=["ui"])
async def user_ui():
    """Serve the participant app."""
    return FileResponse(_UI_DIR / "user" / "index.html")


# ── WebSocket (real-time data feed) ──────────────────────────

@router.websocket("/ws/stream")
async def ws_stream(
    ws: WebSocket,
    channel: str = Query("all"),
):
    """Real-time WebSocket feed with channel subscription.

    Connect to ``/ws/stream?channel=readings`` to receive only
    sensor data, ``channel=alerts`` for alerts, ``channel=affect``
    for affect inferences, or ``channel=all`` (default) for everything.
    """
    await ws_manager.connect(ws, channel)
    logger.info("ws.client_connected", channel=channel, total=ws_manager.active_count)
    try:
        while True:
            # Keep alive; clients are read-only consumers.
            data = await ws.receive_text()
            # Allow clients to switch channels via JSON message.
            if data.startswith("{"):
                try:
                    msg = _json.loads(data)
                    if "channel" in msg:
                        await ws_manager.disconnect(ws)
                        await ws_manager.connect(ws, msg["channel"])
                except _json.JSONDecodeError:
                    pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
        logger.info("ws.client_disconnected", total=ws_manager.active_count)
