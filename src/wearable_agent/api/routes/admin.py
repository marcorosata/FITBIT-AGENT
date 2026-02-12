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


@router.put("/admin/api/tools/metrics/{metric_key}", tags=["admin"])
async def update_metric_info(metric_key: str, body: dict):
    """Update the reference info (label, unit, normal_range, description) for a metric.

    Accepts a JSON body with any subset of: label, unit, normal_range, description.
    Changes are applied to the in-memory _METRIC_INFO dict used by the agent tools.
    """
    from wearable_agent.agent.tools import _METRIC_INFO
    from wearable_agent.models import MetricType

    # Validate metric exists
    valid_keys = {mt.value for mt in MetricType}
    if metric_key not in valid_keys:
        from fastapi import HTTPException
        raise HTTPException(404, f"Unknown metric: {metric_key}")

    info = _METRIC_INFO.setdefault(metric_key, {})
    if "label" in body:
        info["label"] = str(body["label"])
    if "unit" in body:
        info["unit"] = str(body["unit"])
    if "description" in body:
        info["description"] = str(body["description"])
    if "normal_range" in body:
        nr = body["normal_range"]
        if nr is None:
            info["normal_range"] = None
        elif isinstance(nr, (list, tuple)) and len(nr) == 2:
            info["normal_range"] = (float(nr[0]), float(nr[1]))
        else:
            from fastapi import HTTPException
            raise HTTPException(422, "normal_range must be [low, high] or null")

    logger.info("admin.metric_updated", metric=metric_key, fields=list(body.keys()))
    return {"metric": metric_key, "updated": info}


@router.put("/admin/api/tools/components/{component_name}/toggle", tags=["admin"])
async def toggle_component(component_name: str):
    """Start or stop a component by name (scheduler only for now)."""
    from wearable_agent.api.server import _scheduler_service

    if component_name == "SchedulerService":
        if _scheduler_service is None:
            from fastapi import HTTPException
            raise HTTPException(503, "Scheduler not configured.")
        if _scheduler_service._running:
            await _scheduler_service.stop()
            return {"component": component_name, "status": "stopped"}
        else:
            await _scheduler_service.start()
            return {"component": component_name, "status": "running"}

    from fastapi import HTTPException
    raise HTTPException(400, f"Component '{component_name}' cannot be toggled from the admin UI.")


@router.post("/admin/api/tools/test", tags=["admin"])
async def test_tool(body: dict):
    """Invoke an agent tool directly with given parameters and return the result.

    Accepts ``{"tool_name": "...", "parameters": {...}}``.
    """
    from fastapi import HTTPException

    from wearable_agent.api.server import _agent

    tool_name = body.get("tool_name")
    parameters = body.get("parameters", {})

    if not tool_name:
        raise HTTPException(422, "tool_name is required")
    if _agent is None:
        raise HTTPException(503, "Agent not initialised")

    tool = None
    for t in _agent._tools:
        if t.name == tool_name:
            tool = t
            break
    if tool is None:
        raise HTTPException(404, f"Tool '{tool_name}' not found")

    try:
        result = await tool.ainvoke(parameters)
        return {"tool": tool_name, "result": result}
    except Exception as exc:
        logger.error("admin.tool_test_failed", tool=tool_name, error=str(exc))
        raise HTTPException(500, f"Tool execution failed: {exc}")


@router.get("/admin/api/tools", tags=["admin"])
async def get_tools_inventory():
    """Return a complete inventory of all agent tools, API routes, and system components."""
    from wearable_agent.api.server import (
        _affect_pipeline,
        _agent,
        _pipeline,
        _rule_engine,
        _scheduler_service,
    )

    # ── Agent LangChain tools ────────────────────────────────
    agent_tools = []
    if _agent is not None:
        for t in _agent._tools:
            sig = {}
            if hasattr(t, "args_schema") and t.args_schema is not None:
                for name, field in t.args_schema.model_fields.items():
                    sig[name] = {
                        "type": field.annotation.__name__ if hasattr(field.annotation, "__name__") else str(field.annotation),
                        "required": field.is_required(),
                        "default": repr(field.default) if field.default is not None else None,
                    }
            agent_tools.append({
                "name": t.name,
                "description": (t.description or "")[:300],
                "parameters": sig,
                "category": "agent",
            })

    # ── API endpoints ────────────────────────────────────────
    from wearable_agent.api.server import app as _app

    api_routes = []
    for route in _app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            api_routes.append({
                "path": route.path,
                "methods": sorted(route.methods - {"HEAD", "OPTIONS"}),
                "name": getattr(route, "name", ""),
                "summary": getattr(route.endpoint, "__doc__", "") or "",
                "tags": getattr(route, "tags", []),
            })

    # ── System components ────────────────────────────────────
    components = [
        {
            "name": "StreamPipeline",
            "category": "streaming",
            "status": "running" if _pipeline else "stopped",
            "description": "In-memory asyncio.Queue publisher/consumer pipeline for sensor readings.",
            "details": {"pending": _pipeline.pending if _pipeline else 0},
        },
        {
            "name": "WearableAgent",
            "category": "intelligence",
            "status": "ready" if _agent else "not_ready",
            "description": "LangGraph ReAct agent combining rule-based and LLM-powered analysis.",
            "details": {"tool_count": len(_agent._tools) if _agent else 0},
        },
        {
            "name": "RuleEngine",
            "category": "monitoring",
            "status": "active" if _rule_engine else "inactive",
            "description": "Evaluates Python expressions against incoming readings to fire alerts.",
            "details": {"rule_count": len(_rule_engine.list_rules()) if _rule_engine else 0},
        },
        {
            "name": "AffectPipeline",
            "category": "intelligence",
            "status": "ready" if _affect_pipeline else "not_ready",
            "description": "Multi-stage inference pipeline for arousal, stress, valence estimation from physiological signals.",
            "details": {},
        },
        {
            "name": "SchedulerService",
            "category": "collection",
            "status": "running" if (_scheduler_service and _scheduler_service._running) else "stopped",
            "description": "Periodic Fitbit data collection scheduler.",
            "details": {
                "interval_minutes": get_settings().scheduler_collect_interval_minutes,
            },
        },
        {
            "name": "WebSocketManager",
            "category": "streaming",
            "status": "active",
            "description": "Real-time WebSocket broadcast manager with channel subscriptions.",
            "details": {
                "clients": ws_manager.active_count,
                "channels": ws_manager.channel_breakdown(),
            },
        },
        {
            "name": "NotificationDispatcher",
            "category": "monitoring",
            "status": "active",
            "description": "Routes alerts to configured notification channels (WebSocket, log, etc.).",
            "details": {},
        },
        {
            "name": "EMAScheduler",
            "category": "intelligence",
            "status": "active",
            "description": "Ecological Momentary Assessment scheduler for ground-truth affect labels.",
            "details": {},
        },
    ]

    # ── Metric reference info ────────────────────────────────
    from wearable_agent.agent.tools import _METRIC_INFO
    from wearable_agent.models import MetricType

    metrics = []
    for mt in MetricType:
        info = _METRIC_INFO.get(mt.value, {})
        metrics.append({
            "key": mt.value,
            "label": info.get("label", mt.value),
            "unit": info.get("unit", ""),
            "normal_range": info.get("normal_range"),
            "description": info.get("description", ""),
        })

    return {
        "agent_tools": agent_tools,
        "api_routes": api_routes,
        "components": components,
        "metrics": metrics,
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
