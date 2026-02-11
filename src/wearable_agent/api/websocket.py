"""WebSocket connection manager — broadcast readings and alerts to all clients."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect

logger = structlog.get_logger(__name__)


# ── Streaming statistics ─────────────────────────────────────

@dataclass
class ChannelStats:
    """Per-channel message tracking."""
    messages_sent: int = 0
    last_message_at: float | None = None


@dataclass
class StreamStats:
    """Aggregate streaming statistics for admin monitoring."""
    total_inbound: int = 0          # readings entering pipeline (from Fitbit)
    total_outbound: int = 0         # messages broadcast to clients
    per_channel: dict[str, ChannelStats] = field(default_factory=dict)
    started_at: float = field(default_factory=time.monotonic)

    # Rolling throughput tracking (last 60 seconds, 1-second buckets)
    _inbound_ts: deque = field(default_factory=lambda: deque(maxlen=300))
    _outbound_ts: deque = field(default_factory=lambda: deque(maxlen=300))

    def record_inbound(self) -> None:
        self.total_inbound += 1
        self._inbound_ts.append(time.monotonic())

    def record_outbound(self, channel: str) -> None:
        self.total_outbound += 1
        now = time.monotonic()
        self._outbound_ts.append(now)
        if channel not in self.per_channel:
            self.per_channel[channel] = ChannelStats()
        ch = self.per_channel[channel]
        ch.messages_sent += 1
        ch.last_message_at = now

    def inbound_rate(self, window: float = 60.0) -> float:
        """Messages per second over the last *window* seconds."""
        cutoff = time.monotonic() - window
        count = sum(1 for t in self._inbound_ts if t > cutoff)
        return count / window

    def outbound_rate(self, window: float = 60.0) -> float:
        cutoff = time.monotonic() - window
        count = sum(1 for t in self._outbound_ts if t > cutoff)
        return count / window

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            "uptime_seconds": round(now - self.started_at),
            "total_inbound": self.total_inbound,
            "total_outbound": self.total_outbound,
            "inbound_rate_per_sec": round(self.inbound_rate(), 2),
            "outbound_rate_per_sec": round(self.outbound_rate(), 2),
            "channels": {
                ch: {
                    "messages_sent": s.messages_sent,
                    "last_message_ago_sec": round(now - s.last_message_at)
                    if s.last_message_at else None,
                }
                for ch, s in self.per_channel.items()
            },
        }


# ── Recent message buffer ────────────────────────────────────

@dataclass
class StreamMessage:
    """Lightweight record of a broadcast message for admin replay."""
    direction: str          # "inbound" | "outbound"
    channel: str
    msg_type: str           # "reading" | "alert" | "affect" | "system"
    summary: str            # short human string
    timestamp: str          # ISO
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "channel": self.channel,
            "type": self.msg_type,
            "summary": self.summary,
            "timestamp": self.timestamp,
            "data": self.data,
        }


class ConnectionManager:
    """Manage WebSocket connections and broadcast messages.

    Supports multiple named channels so clients can subscribe selectively.
    Default channels: ``readings``, ``alerts``, ``affect``, ``system``.
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._all: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self.stats = StreamStats()
        self._recent: deque[StreamMessage] = deque(maxlen=200)

    # ── Connection lifecycle ──────────────────────────────────

    async def connect(self, ws: WebSocket, channels: str | list[str] | None = None) -> None:
        """Accept a WebSocket and subscribe to channels."""
        await ws.accept()
        if isinstance(channels, str):
            channels = [channels]
        async with self._lock:
            self._all.append(ws)
            for ch in (channels or ["all"]):
                self._connections.setdefault(ch, []).append(ws)
        logger.info("ws.connected", total=len(self._all), channels=channels or ["all"])

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket from all channels."""
        async with self._lock:
            if ws in self._all:
                self._all.remove(ws)
            for ch_list in self._connections.values():
                if ws in ch_list:
                    ch_list.remove(ws)
        logger.info("ws.disconnected", total=len(self._all))

    @property
    def client_count(self) -> int:
        return len(self._all)

    @property
    def active_count(self) -> int:
        """Alias for client_count (used by server.py)."""
        return len(self._all)

    def channel_breakdown(self) -> dict[str, int]:
        """Return number of subscribers per channel."""
        return {ch: len(subs) for ch, subs in self._connections.items() if subs}

    # ── Inbound tracking ─────────────────────────────────────

    def record_inbound(self, reading_data: dict[str, Any]) -> None:
        """Track a reading arriving from Fitbit / pipeline."""
        self.stats.record_inbound()
        self._recent.appendleft(StreamMessage(
            direction="inbound",
            channel="pipeline",
            msg_type=reading_data.get("metric_type", "reading"),
            summary=f'{reading_data.get("participant_id","?")} '
                    f'{reading_data.get("metric_type","?")} = '
                    f'{reading_data.get("value","?")} '
                    f'{reading_data.get("unit","")}',
            timestamp=reading_data.get("timestamp", datetime.utcnow().isoformat()),
            data=reading_data,
        ))

    # ── Broadcasting ──────────────────────────────────────────

    async def broadcast(self, message: dict[str, Any], channel: str = "all") -> None:
        """Send a JSON message to all clients on a channel."""
        targets = self._connections.get(channel, []) if channel != "all" else self._all
        if not targets:
            return

        payload = json.dumps(message, default=_json_default)
        dead: list[WebSocket] = []

        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        # Track (avoid double-counting by tracking only named channels, not "all")
        if channel != "all":
            self.stats.record_outbound(channel)

        # Clean up dead connections
        for ws in dead:
            await self.disconnect(ws)

    async def broadcast_reading(self, reading_data: dict[str, Any]) -> None:
        """Broadcast a sensor reading to the 'readings' and 'all' channels."""
        msg = {"type": "reading", "data": reading_data}
        self._recent.appendleft(StreamMessage(
            direction="outbound",
            channel="readings",
            msg_type="reading",
            summary=f'→ {reading_data.get("participant_id","?")} '
                    f'{reading_data.get("metric_type","?")} = '
                    f'{reading_data.get("value","?")}',
            timestamp=reading_data.get("timestamp", datetime.utcnow().isoformat()),
            data=reading_data,
        ))
        await self.broadcast(msg, "readings")
        await self.broadcast(msg, "all")

    async def broadcast_alert(self, alert_data: dict[str, Any]) -> None:
        """Broadcast an alert to the 'alerts' and 'all' channels."""
        msg = {"type": "alert", "data": alert_data}
        self._recent.appendleft(StreamMessage(
            direction="outbound",
            channel="alerts",
            msg_type="alert",
            summary=f'⚠ {alert_data.get("participant_id","?")} '
                    f'{alert_data.get("severity","?")} — '
                    f'{alert_data.get("message","?")}',
            timestamp=alert_data.get("timestamp", datetime.utcnow().isoformat()),
            data=alert_data,
        ))
        await self.broadcast(msg, "alerts")
        await self.broadcast(msg, "all")

    async def broadcast_affect(self, affect_data: dict[str, Any]) -> None:
        """Broadcast an affect inference result."""
        msg = {"type": "affect", "data": affect_data}
        self._recent.appendleft(StreamMessage(
            direction="outbound",
            channel="affect",
            msg_type="affect",
            summary=f'🧠 {affect_data.get("participant_id","?")} affect inference',
            timestamp=datetime.utcnow().isoformat(),
            data=affect_data,
        ))
        await self.broadcast(msg, "affect")
        await self.broadcast(msg, "all")

    async def broadcast_system(self, event: str, details: dict[str, Any] | None = None) -> None:
        """Broadcast a system event (sync status, errors, etc.)."""
        msg = {"type": "system", "event": event, "data": details or {}}
        self._recent.appendleft(StreamMessage(
            direction="outbound",
            channel="system",
            msg_type="system",
            summary=f'⚙ {event}',
            timestamp=datetime.utcnow().isoformat(),
            data=details,
        ))
        await self.broadcast(msg, "system")
        await self.broadcast(msg, "all")

    # ── Admin helpers ─────────────────────────────────────────

    def get_recent_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the N most recent stream messages for admin display."""
        return [m.to_dict() for m in list(self._recent)[:limit]]


# ── Shared instance ──────────────────────────────────────────

ws_manager = ConnectionManager()


def _json_default(obj: Any) -> Any:
    """Fallback JSON serialiser for datetime etc."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serialisable: {type(obj)}")
