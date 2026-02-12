"""Async data-streaming pipeline connecting collectors → storage → agent."""

from __future__ import annotations

import asyncio
from typing import Callable, Awaitable

import structlog

from wearable_agent.models import SensorReading

logger = structlog.get_logger(__name__)


class StreamPipeline:
    """In-process async pipeline that buffers sensor readings, persists them,
    and forwards them to registered observers (e.g. the monitoring agent).

    The pipeline decouples producers (collectors) from consumers (monitors,
    storage) using an :class:`asyncio.Queue`.
    """

    def __init__(self, maxsize: int = 10_000) -> None:
        self._queue: asyncio.Queue[SensorReading] = asyncio.Queue(maxsize=maxsize)
        self._consumers: list[Callable[[SensorReading], Awaitable[None]]] = []
        self._running = False

    # ── Configuration ─────────────────────────────────────────

    def add_consumer(self, fn: Callable[[SensorReading], Awaitable[None]]) -> None:
        """Register an async callback that receives every reading."""
        self._consumers.append(fn)

    # ── Producer side ─────────────────────────────────────────

    async def publish(self, reading: SensorReading) -> None:
        """Enqueue a reading for downstream processing."""
        await self._queue.put(reading)

    async def publish_batch(self, readings: list[SensorReading]) -> None:
        for r in readings:
            await self._queue.put(r)

    # ── Consumer loop ─────────────────────────────────────────

    async def start(self) -> None:
        """Start the consumer loop (run as a background task)."""
        import time

        self._running = True
        self._processed_total = 0
        logger.info("stream_pipeline.started", consumers=len(self._consumers))

        last_stats_time = time.monotonic()

        while self._running:
            try:
                reading = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            for consumer in self._consumers:
                try:
                    await consumer(reading)
                except Exception as exc:
                    logger.error(
                        "stream_pipeline.consumer_error",
                        consumer=consumer.__qualname__,
                        error=str(exc),
                    )

            self._processed_total += 1
            self._queue.task_done()

            # Periodic stats every 60 seconds
            now = time.monotonic()
            if now - last_stats_time >= 60:
                logger.info(
                    "stream_pipeline.stats",
                    processed_total=self._processed_total,
                    queue_pending=self._queue.qsize(),
                )
                last_stats_time = now

    async def stop(self) -> None:
        """Gracefully stop the consumer loop."""
        self._running = False
        logger.info("stream_pipeline.stopped")

    @property
    def pending(self) -> int:
        return self._queue.qsize()
