"""Scheduler service — periodic Fitbit data collection via APScheduler.

Architecture
~~~~~~~~~~~~
The ``SchedulerService`` runs as a background component within the
FastAPI lifespan.  Every ``scheduler_collect_interval_minutes`` it:

1. Loads all active participants with valid Fitbit tokens.
2. For each participant (up to ``max_concurrent_syncs`` at a time):
   a. Authenticates the ``FitbitCollector`` with stored tokens.
   b. Fetches today's data for all configured metrics.
   c. Publishes readings to the ``StreamPipeline``.
   d. Auto-refreshes expired tokens.
   e. Updates ``last_sync`` timestamp.

Token refresh failures are logged but do not block other participants.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from wearable_agent.collectors.fitbit import FitbitCollector
from wearable_agent.config import get_settings
from wearable_agent.models import MetricType
from wearable_agent.storage.repository import ParticipantRepository, TokenRepository

logger = structlog.get_logger(__name__)

# All metrics to collect on each sync
_SYNC_METRICS = [
    MetricType.HEART_RATE,
    MetricType.STEPS,
    MetricType.CALORIES,
    MetricType.DISTANCE,
    MetricType.FLOORS,
    MetricType.ACTIVE_ZONE_MINUTES,
    MetricType.SLEEP,
    MetricType.SPO2,
    MetricType.HRV,
    MetricType.SKIN_TEMPERATURE,
    MetricType.BREATHING_RATE,
]


class SchedulerService:
    """Background service for periodic Fitbit data collection.

    Integration::

        scheduler = SchedulerService(pipeline)
        await scheduler.start()
        ...
        await scheduler.stop()
    """

    def __init__(
        self,
        pipeline: Any | None = None,  # StreamPipeline — avoid circular import
        affect_pipeline: Any | None = None,
        interval_minutes: int | None = None,
        max_concurrent: int | None = None,
    ) -> None:
        settings = get_settings()
        self._pipeline = pipeline
        self._affect_pipeline = affect_pipeline
        self._interval = interval_minutes or settings.scheduler_collect_interval_minutes
        self._max_concurrent = max_concurrent or settings.scheduler_max_concurrent_syncs
        self._running = False
        self._task: asyncio.Task | None = None

        self._participant_repo = ParticipantRepository()
        self._token_repo = TokenRepository()

        # Track sync stats
        self._stats = {
            "last_run": None,
            "total_runs": 0,
            "last_readings_count": 0,
            "last_errors": 0,
            "active_syncs": 0,
        }

    # ── Lifecycle ─────────────────────────────────────────────

    async def start(self) -> None:
        """Start the periodic collection loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "scheduler.started",
            interval_minutes=self._interval,
            max_concurrent=self._max_concurrent,
        )

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("scheduler.stopped")

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Main loop ─────────────────────────────────────────────

    async def _run_loop(self) -> None:
        """Run the collection loop forever."""
        while self._running:
            try:
                await self._collect_all()
            except Exception:
                logger.exception("scheduler.run_error")

            # Wait for next interval
            await asyncio.sleep(self._interval * 60)

    async def _collect_all(self) -> None:
        """Run one collection cycle for all active participants."""
        participants = await self._participant_repo.list_all(active_only=True)
        if not participants:
            logger.debug("scheduler.no_participants")
            return

        self._stats["total_runs"] += 1
        self._stats["last_run"] = datetime.now(UTC).isoformat()
        total_readings = 0
        total_errors = 0

        # Limit concurrency
        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def _sync_one(participant_id: str) -> tuple[int, int]:
            async with semaphore:
                return await self._sync_participant(participant_id)

        tasks = [_sync_one(p.participant_id) for p in participants]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                total_errors += 1
                logger.error("scheduler.participant_error", error=str(result))
            else:
                readings_count, errors = result
                total_readings += readings_count
                total_errors += errors

        self._stats["last_readings_count"] = total_readings
        self._stats["last_errors"] = total_errors
        logger.info(
            "scheduler.cycle_complete",
            participants=len(participants),
            readings=total_readings,
            errors=total_errors,
        )

    # ── Per-participant sync ──────────────────────────────────

    async def _sync_participant(self, participant_id: str) -> tuple[int, int]:
        """Sync data for a single participant.

        Returns (readings_count, error_count).
        """
        errors = 0

        # 1. Load tokens
        token_row = await self._token_repo.get(participant_id, "fitbit")
        if token_row is None:
            logger.warning("scheduler.no_token", participant=participant_id)
            return 0, 1

        # 2. Check & refresh expired tokens
        access_token = token_row.access_token
        refresh_token = token_row.refresh_token

        if token_row.expires_at and token_row.expires_at < datetime.utcnow():
            if refresh_token:
                try:
                    access_token, refresh_token = await self._refresh_token(
                        participant_id, refresh_token
                    )
                except Exception:
                    logger.exception("scheduler.refresh_failed", participant=participant_id)
                    return 0, 1
            else:
                logger.warning("scheduler.token_expired_no_refresh", participant=participant_id)
                return 0, 1

        # 3. Collect data
        collector = FitbitCollector()
        try:
            await collector.authenticate(
                access_token=access_token,
                refresh_token=refresh_token,
            )
            readings = await collector.fetch(participant_id, _SYNC_METRICS)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401 and refresh_token:
                # Token likely expired during request — try refresh & retry
                try:
                    access_token, refresh_token = await self._refresh_token(
                        participant_id, refresh_token
                    )
                    await collector.close()
                    collector = FitbitCollector()
                    await collector.authenticate(
                        access_token=access_token,
                        refresh_token=refresh_token,
                    )
                    readings = await collector.fetch(participant_id, _SYNC_METRICS)
                except Exception:
                    logger.exception("scheduler.retry_failed", participant=participant_id)
                    return 0, 1
            else:
                logger.error(
                    "scheduler.fetch_error",
                    participant=participant_id,
                    status=exc.response.status_code,
                )
                return 0, 1
        except Exception:
            logger.exception("scheduler.fetch_error", participant=participant_id)
            return 0, 1
        finally:
            await collector.close()

        # 4. Publish to pipeline
        if readings and self._pipeline:
            await self._pipeline.publish_batch(readings)

        # 5. Update last_sync
        await self._participant_repo.update_last_sync(
            participant_id, datetime.utcnow()
        )

        logger.info(
            "scheduler.sync_complete",
            participant=participant_id,
            readings=len(readings),
        )
        return len(readings), errors

    # ── Token refresh ─────────────────────────────────────────

    async def _refresh_token(
        self, participant_id: str, refresh_token: str
    ) -> tuple[str, str]:
        """Refresh Fitbit tokens and persist the new pair.

        Returns (new_access_token, new_refresh_token).
        """
        settings = get_settings()
        basic = base64.b64encode(
            f"{settings.fitbit_client_id}:{settings.fitbit_client_secret}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.fitbit.com/oauth2/token",
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            body = resp.json()

        new_access = body["access_token"]
        new_refresh = body.get("refresh_token", refresh_token)
        expires_at = datetime.utcnow() + timedelta(seconds=body.get("expires_in", 28800))

        await self._token_repo.upsert(
            participant_id=participant_id,
            access_token=new_access,
            refresh_token=new_refresh,
            provider="fitbit",
            expires_at=expires_at,
            scopes=body.get("scope", ""),
        )

        logger.info("scheduler.token_refreshed", participant=participant_id)
        return new_access, new_refresh

    # ── Manual trigger ────────────────────────────────────────

    async def trigger_sync(self, participant_id: str) -> dict[str, Any]:
        """Manually trigger an immediate sync for a single participant."""
        readings_count, errors = await self._sync_participant(participant_id)
        return {
            "participant_id": participant_id,
            "readings": readings_count,
            "errors": errors,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def trigger_sync_all(self) -> dict[str, Any]:
        """Manually trigger an immediate sync for all active participants."""
        await self._collect_all()
        return {
            "status": "complete",
            "stats": self.stats,
        }
