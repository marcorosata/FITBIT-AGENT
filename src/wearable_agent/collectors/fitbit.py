"""Fitbit Web API collector — OAuth 2.0, rate limiting, full metric coverage.

Implements the Fitbit Web API v1/v1.2 endpoints for:
  Activity (steps, calories, distance, floors, active zone minutes),
  Heart Rate (time-series + intraday), HRV, SpO₂, Sleep,
  Skin Temperature, Breathing Rate, Body (weight, fat), VO₂ Max.

See: https://dev.fitbit.com/build/reference/web-api/
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from wearable_agent.collectors.base import BaseCollector
from wearable_agent.collectors.fitbit_oauth import refresh_fitbit_token
from wearable_agent.config import get_settings
from wearable_agent.models import DeviceType, MetricType, SensorReading

logger = structlog.get_logger(__name__)


# ── Fitbit endpoint templates ─────────────────────────────────
# Keys are MetricType values; values are (url_template, api_version) pairs.
# {date} is replaced with YYYY-MM-DD at request time.

_ENDPOINTS: dict[MetricType, str] = {
    # Activity time-series (v1)
    MetricType.HEART_RATE: "/1/user/-/activities/heart/date/{date}/1d/1min.json",
    MetricType.STEPS: "/1/user/-/activities/steps/date/{date}/1d.json",
    MetricType.CALORIES: "/1/user/-/activities/calories/date/{date}/1d.json",
    MetricType.DISTANCE: "/1/user/-/activities/distance/date/{date}/1d.json",
    MetricType.FLOORS: "/1/user/-/activities/floors/date/{date}/1d.json",
    MetricType.ACTIVE_ZONE_MINUTES: "/1/user/-/activities/active-zone-minutes/date/{date}/1d.json",
    # Sleep (v1.2)
    MetricType.SLEEP: "/1.2/user/-/sleep/date/{date}.json",
    # SpO₂
    MetricType.SPO2: "/1/user/-/spo2/date/{date}.json",
    # Heart Rate Variability
    MetricType.HRV: "/1/user/-/hrv/date/{date}.json",
    # Skin Temperature
    MetricType.SKIN_TEMPERATURE: "/1/user/-/temp/skin/date/{date}.json",
    # Breathing Rate
    MetricType.BREATHING_RATE: "/1/user/-/br/date/{date}.json",
    # Body
    MetricType.BODY_WEIGHT: "/1/user/-/body/log/weight/date/{date}.json",
    MetricType.BODY_FAT: "/1/user/-/body/log/fat/date/{date}.json",
    # VO₂ Max (Cardio Fitness Score)
    MetricType.VO2_MAX: "/1/user/-/cardioscore/date/{date}.json",
}

# Date-range endpoint templates for time-series queries.
# {start} and {end} are replaced at request time.
_RANGE_ENDPOINTS: dict[MetricType, str] = {
    MetricType.HEART_RATE: "/1/user/-/activities/heart/date/{start}/{end}.json",
    MetricType.STEPS: "/1/user/-/activities/steps/date/{start}/{end}.json",
    MetricType.CALORIES: "/1/user/-/activities/calories/date/{start}/{end}.json",
    MetricType.DISTANCE: "/1/user/-/activities/distance/date/{start}/{end}.json",
    MetricType.FLOORS: "/1/user/-/activities/floors/date/{start}/{end}.json",
    MetricType.SLEEP: "/1.2/user/-/sleep/date/{start}/{end}.json",
    MetricType.SPO2: "/1/user/-/spo2/date/{start}/{end}.json",
    MetricType.HRV: "/1/user/-/hrv/date/{start}/{end}.json",
    MetricType.SKIN_TEMPERATURE: "/1/user/-/temp/skin/date/{start}/{end}.json",
    MetricType.BREATHING_RATE: "/1/user/-/br/date/{start}/{end}.json",
    MetricType.BODY_WEIGHT: "/1/user/-/body/log/weight/date/{start}/{end}.json",
    MetricType.BODY_FAT: "/1/user/-/body/log/fat/date/{start}/{end}.json",
    MetricType.VO2_MAX: "/1/user/-/cardioscore/date/{start}/{end}.json",
}


# ── Rate-limit tracker ────────────────────────────────────────


class _RateLimiter:
    """Track Fitbit rate-limit headers and enforce back-off.

    Fitbit returns these headers on every response:
      fitbit-rate-limit-limit       – requests allowed per hour
      fitbit-rate-limit-remaining   – requests remaining in window
      fitbit-rate-limit-reset       – seconds until the window resets
    """

    def __init__(self, max_per_hour: int = 150) -> None:
        self.limit = max_per_hour
        self.remaining = max_per_hour
        self.reset_at: float = 0.0  # epoch timestamp when window resets

    def update(self, headers: httpx.Headers) -> None:
        """Update state from Fitbit response headers."""
        if "fitbit-rate-limit-remaining" in headers:
            self.remaining = int(headers["fitbit-rate-limit-remaining"])
        if "fitbit-rate-limit-limit" in headers:
            self.limit = int(headers["fitbit-rate-limit-limit"])
        if "fitbit-rate-limit-reset" in headers:
            self.reset_at = time.monotonic() + int(headers["fitbit-rate-limit-reset"])

    async def wait_if_needed(self) -> None:
        """Sleep if we're close to the rate limit."""
        if self.remaining <= 1 and self.reset_at > time.monotonic():
            wait = self.reset_at - time.monotonic()
            logger.warning("fitbit.rate_limit_near", wait_seconds=round(wait, 1))
            await asyncio.sleep(wait)


# ── Collector ─────────────────────────────────────────────────


class FitbitCollector(BaseCollector):
    """Collects data from the Fitbit Web API.

    Supports the full OAuth 2.0 Authorization Code Grant flow including
    automatic token refresh, per-user rate-limit tracking, and parsers
    for every metric type in the Fitbit API.

    Usage::

        collector = FitbitCollector()
        await collector.authenticate(access_token="...", refresh_token="...")
        readings = await collector.fetch("P001", [MetricType.HEART_RATE])
    """

    device_type = DeviceType.FITBIT

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._rate_limiter = _RateLimiter()

    # ── Auth ──────────────────────────────────────────────────

    async def authenticate(self, **credentials: str) -> None:  # type: ignore[override]
        """Store the OAuth 2.0 tokens and create an HTTP client.

        Required keyword: ``access_token``.
        Optional keyword: ``refresh_token`` (enables automatic renewal).
        """
        settings = get_settings()
        self._access_token = credentials.get("access_token") or settings.fitbit_access_token
        self._refresh_token = credentials.get("refresh_token") or settings.fitbit_refresh_token

        if not self._access_token:
            raise ValueError(
                "No access_token provided via argument or FITBIT_ACCESS_TOKEN env var."
            )

        self._rate_limiter = _RateLimiter(settings.fitbit_rate_limit_per_hour)
        self._client = httpx.AsyncClient(
            base_url=settings.fitbit_api_base_url,
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=settings.fitbit_request_timeout,
        )
        logger.info("fitbit_collector.authenticated")

    async def refresh_access_token(self) -> str:
        """Exchange the refresh token for a new access/refresh token pair.

        Uses the shared :func:`refresh_fitbit_token` helper.  After the
        HTTP exchange, updates instance state and re-creates the HTTP
        client with the new bearer token.

        Returns the new access token.
        """
        if not self._refresh_token:
            raise RuntimeError("No refresh_token available — cannot renew.")

        settings = get_settings()
        body = await refresh_fitbit_token(
            refresh_token=self._refresh_token,
            client_id=settings.fitbit_client_id,
            client_secret=settings.fitbit_client_secret,
            timeout=settings.fitbit_request_timeout,
        )

        self._access_token = body["access_token"]
        self._refresh_token = body.get("refresh_token", self._refresh_token)

        # Re-create the HTTP client with the new token
        if self._client:
            await self._client.aclose()
        self._client = httpx.AsyncClient(
            base_url=settings.fitbit_api_base_url,
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=settings.fitbit_request_timeout,
        )
        logger.info("fitbit_collector.token_refreshed")
        return self._access_token

    # ── Internal request wrapper ──────────────────────────────

    async def _request(self, url: str) -> dict[str, Any]:
        """GET a Fitbit endpoint with rate-limit tracking and auto-refresh.

        Handles:
          - 429 Too Many Requests → wait for rate-limit reset, retry once
          - 401 Unauthorized      → attempt token refresh, retry once
        """
        if self._client is None:
            raise RuntimeError("Call authenticate() before making requests.")

        await self._rate_limiter.wait_if_needed()

        resp = await self._client.get(url)
        self._rate_limiter.update(resp.headers)

        # Handle 429 — rate limited
        if resp.status_code == 429:
            reset = int(resp.headers.get("fitbit-rate-limit-reset", "60"))
            logger.warning("fitbit.rate_limited", retry_after=reset)
            await asyncio.sleep(reset)
            resp = await self._client.get(url)
            self._rate_limiter.update(resp.headers)

        # Handle 401 — token expired
        if resp.status_code == 401 and self._refresh_token:
            logger.info("fitbit.token_expired_refreshing")
            await self.refresh_access_token()
            resp = await self._client.get(url)
            self._rate_limiter.update(resp.headers)

        resp.raise_for_status()
        return resp.json()

    # ── Fetch (single date) ───────────────────────────────────

    async def fetch(
        self,
        participant_id: str,
        metrics: list[MetricType],
        *,
        date: str | None = None,
    ) -> list[SensorReading]:
        """Fetch readings for one date across one or more metric types."""
        target_date = date or datetime.now(UTC).strftime("%Y-%m-%d")
        readings: list[SensorReading] = []

        for metric in metrics:
            endpoint = _ENDPOINTS.get(metric)
            if endpoint is None:
                logger.warning("fitbit_collector.unsupported_metric", metric=metric.value)
                continue

            url = endpoint.format(date=target_date)
            data = await self._request(url)
            readings.extend(self._parse(participant_id, metric, data, target_date))

        logger.info(
            "fitbit_collector.fetched",
            participant=participant_id,
            count=len(readings),
            date=target_date,
        )
        return readings

    # ── Fetch date range ──────────────────────────────────────

    async def fetch_range(
        self,
        participant_id: str,
        metrics: list[MetricType],
        start_date: str,
        end_date: str,
    ) -> list[SensorReading]:
        """Fetch readings for a date range across one or more metric types.

        Parameters
        ----------
        start_date, end_date:
            ISO date strings (``YYYY-MM-DD``).
        """
        readings: list[SensorReading] = []

        for metric in metrics:
            endpoint = _RANGE_ENDPOINTS.get(metric)
            if endpoint is None:
                logger.warning("fitbit_collector.no_range_endpoint", metric=metric.value)
                continue

            url = endpoint.format(start=start_date, end=end_date)
            data = await self._request(url)
            readings.extend(self._parse(participant_id, metric, data, start_date))

        logger.info(
            "fitbit_collector.fetched_range",
            participant=participant_id,
            count=len(readings),
            start=start_date,
            end=end_date,
        )
        return readings

    # ── Device info ───────────────────────────────────────────

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get all Fitbit devices linked to the user's account.

        GET /1/user/-/devices.json
        """
        return await self._request("/1/user/-/devices.json")  # type: ignore[return-value]

    # ── Parsers ───────────────────────────────────────────────

    def _parse(
        self,
        participant_id: str,
        metric: MetricType,
        data: dict[str, Any],
        date_str: str,
    ) -> list[SensorReading]:
        """Dispatch to the appropriate metric-specific parser."""
        # Check for a specialised parser first, then fall back to the
        # declarative simple-parser table.
        specialised = _SPECIALISED_PARSERS.get(metric)
        if specialised is not None:
            return specialised(self, participant_id, data, date_str)

        spec = _SIMPLE_PARSERS.get(metric)
        if spec is not None:
            return self._parse_simple_timeseries(participant_id, data, date_str, spec)

        logger.warning("fitbit_collector.no_parser", metric=metric.value)
        return []

    # ── Generic simple-timeseries parser ──────────────────────

    @staticmethod
    def _parse_simple_timeseries(
        pid: str,
        data: dict[str, Any],
        date_str: str,
        spec: "_SimpleParserSpec",
    ) -> list[SensorReading]:
        """Parse any Fitbit timeseries that follows a regular pattern.

        The *spec* descriptor tells this method where to find entries,
        how to extract the numeric value, and how to build the timestamp.
        """
        readings: list[SensorReading] = []
        for entry in data.get(spec.data_key, []):
            # --- Extract numeric value --------------------------------
            if spec.value_path:
                # Nested value object: walk the key path
                obj = entry
                for key in spec.value_path:
                    obj = obj.get(key, {}) if isinstance(obj, dict) else None
                    if obj is None:
                        break
                if obj is None:
                    continue
                val = float(obj)
            elif spec.value_key:
                # Body-log style: the value is a top-level key in the entry
                raw = entry.get(spec.value_key)
                if raw is None:
                    continue
                val = float(raw)
            else:
                # Flat timeseries: value is entry["value"]
                val = float(entry["value"])

            # --- Build timestamp --------------------------------------
            if spec.ts_from_date_time_keys:
                # Body-log style: separate "date" and "time" keys
                ts_str = f"{entry['date']}T{entry.get('time', '00:00:00')}"
                ts = datetime.fromisoformat(ts_str)
            else:
                dt = entry.get("dateTime", date_str)
                ts = datetime.fromisoformat(dt)

            # --- Extract optional metadata ----------------------------
            meta: dict[str, Any] = {}
            if spec.metadata_extractor is not None:
                meta = spec.metadata_extractor(entry)

            readings.append(
                SensorReading(
                    participant_id=pid,
                    device_type=DeviceType.FITBIT,
                    metric_type=spec.metric_type,
                    value=val,
                    unit=spec.unit,
                    timestamp=ts,
                    metadata=meta,
                )
            )
        return readings

    # ── Specialised parsers (unique logic) ────────────────────

    def _parse_heart_rate(
        self, pid: str, data: dict[str, Any], date_str: str
    ) -> list[SensorReading]:
        readings: list[SensorReading] = []
        # Intraday dataset (1-min resolution) — requires intraday scope
        intraday = data.get("activities-heart-intraday", {}).get("dataset", [])
        for point in intraday:
            ts = datetime.fromisoformat(f"{date_str}T{point['time']}")
            readings.append(
                SensorReading(
                    participant_id=pid,
                    device_type=DeviceType.FITBIT,
                    metric_type=MetricType.HEART_RATE,
                    value=float(point["value"]),
                    unit="bpm",
                    timestamp=ts,
                )
            )

        # Daily resting HR from the summary (always available)
        for day in data.get("activities-heart", []):
            resting = day.get("value", {}).get("restingHeartRate")
            if resting is not None:
                ts = datetime.fromisoformat(day["dateTime"])
                readings.append(
                    SensorReading(
                        participant_id=pid,
                        device_type=DeviceType.FITBIT,
                        metric_type=MetricType.HEART_RATE,
                        value=float(resting),
                        unit="bpm",
                        timestamp=ts,
                        metadata={
                            "type": "resting",
                            "zones": day.get("value", {}).get(
                                "heartRateZones", []
                            ),
                        },
                    )
                )
        return readings

    def _parse_sleep(
        self, pid: str, data: dict[str, Any], date_str: str
    ) -> list[SensorReading]:
        """Parse sleep log entries — returns one reading per sleep period.

        The value is total minutes asleep.  Detailed stage data (deep, light,
        rem, wake) is stored in ``metadata``.
        """
        readings: list[SensorReading] = []
        for log in data.get("sleep", []):
            ts_str = log.get("startTime", date_str)
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                ts = datetime.fromisoformat(date_str)

            summary = log.get("levels", {}).get("summary", {})
            readings.append(
                SensorReading(
                    participant_id=pid,
                    device_type=DeviceType.FITBIT,
                    metric_type=MetricType.SLEEP,
                    value=float(log.get("minutesAsleep", 0)),
                    unit="minutes",
                    timestamp=ts,
                    metadata={
                        "efficiency": log.get("efficiency"),
                        "duration_ms": log.get("duration"),
                        "type": log.get("type"),  # "stages" or "classic"
                        "deep_minutes": summary.get("deep", {}).get("minutes"),
                        "light_minutes": summary.get("light", {}).get("minutes"),
                        "rem_minutes": summary.get("rem", {}).get("minutes"),
                        "wake_minutes": summary.get("wake", {}).get("minutes"),
                    },
                )
            )
        return readings

    def _parse_spo2(
        self, pid: str, data: dict[str, Any], date_str: str
    ) -> list[SensorReading]:
        """Parse SpO₂ summary — min, max, avg stored in metadata."""
        readings: list[SensorReading] = []
        # Single-date response has a top-level dict or a list
        items = data if isinstance(data, list) else [data]
        for item in items:
            value_obj = item.get("value", item)
            avg = value_obj.get("avg")
            if avg is None:
                continue
            dt = item.get("dateTime", date_str)
            ts = datetime.fromisoformat(dt) if "T" in dt else datetime.fromisoformat(dt)
            readings.append(
                SensorReading(
                    participant_id=pid,
                    device_type=DeviceType.FITBIT,
                    metric_type=MetricType.SPO2,
                    value=float(avg),
                    unit="%",
                    timestamp=ts,
                    metadata={
                        "min": value_obj.get("min"),
                        "max": value_obj.get("max"),
                    },
                )
            )
        return readings

    # ── Lifecycle ─────────────────────────────────────────────

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# ── Simple parser descriptors ────────────────────────────────
#
# Each _SimpleParserSpec declares how to extract readings from a
# standard Fitbit timeseries response, eliminating the need for
# a separate method per metric.  Specialised parsers for heart_rate,
# sleep, and spo2 remain as methods above.

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True, slots=True)
class _SimpleParserSpec:
    """Descriptor for a simple Fitbit timeseries parser."""

    metric_type: MetricType
    data_key: str
    unit: str
    # For nested value objects (e.g. {"value": {"dailyRmssd": 42}}),
    # specify the key path as a tuple: ("value", "dailyRmssd").
    value_path: tuple[str, ...] | None = None
    # For body-log style where the value key differs from "value".
    value_key: str | None = None
    # Whether the timestamp is built from separate "date" + "time" keys
    # (body logs) vs the usual "dateTime" key.
    ts_from_date_time_keys: bool = False
    # Optional callable to extract metadata from each entry dict.
    metadata_extractor: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _azm_metadata(entry: dict[str, Any]) -> dict[str, Any]:
    """Extract AZM zone breakdown from an active-zone-minutes entry."""
    val = entry.get("value", {})
    if not isinstance(val, dict):
        return {}
    return {
        "fat_burn_minutes": val.get("fatBurnActiveZoneMinutes"),
        "cardio_minutes": val.get("cardioActiveZoneMinutes"),
        "peak_minutes": val.get("peakActiveZoneMinutes"),
    }


_SIMPLE_PARSERS: dict[MetricType, _SimpleParserSpec] = {
    # ── Flat timeseries (dateTime + value) ─────────────────
    MetricType.STEPS: _SimpleParserSpec(
        metric_type=MetricType.STEPS,
        data_key="activities-steps",
        unit="steps",
    ),
    MetricType.CALORIES: _SimpleParserSpec(
        metric_type=MetricType.CALORIES,
        data_key="activities-calories",
        unit="kcal",
    ),
    MetricType.DISTANCE: _SimpleParserSpec(
        metric_type=MetricType.DISTANCE,
        data_key="activities-distance",
        unit="km",
    ),
    MetricType.FLOORS: _SimpleParserSpec(
        metric_type=MetricType.FLOORS,
        data_key="activities-floors",
        unit="floors",
    ),
    # ── Nested-value timeseries ────────────────────────────
    MetricType.HRV: _SimpleParserSpec(
        metric_type=MetricType.HRV,
        data_key="hrv",
        unit="ms",
        value_path=("value", "dailyRmssd"),
    ),
    MetricType.SKIN_TEMPERATURE: _SimpleParserSpec(
        metric_type=MetricType.SKIN_TEMPERATURE,
        data_key="tempSkin",
        unit="°C",
        value_path=("value", "nightlyRelative"),
    ),
    MetricType.BREATHING_RATE: _SimpleParserSpec(
        metric_type=MetricType.BREATHING_RATE,
        data_key="br",
        unit="brpm",
        value_path=("value", "breathingRate"),
    ),
    MetricType.VO2_MAX: _SimpleParserSpec(
        metric_type=MetricType.VO2_MAX,
        data_key="cardioScore",
        unit="mL/kg/min",
        value_path=("value", "vo2Max"),
    ),
    # ── Body logs (date + time keys) ──────────────────────
    MetricType.BODY_WEIGHT: _SimpleParserSpec(
        metric_type=MetricType.BODY_WEIGHT,
        data_key="weight",
        unit="kg",
        value_key="weight",
        ts_from_date_time_keys=True,
        metadata_extractor=lambda e: {"bmi": e.get("bmi"), "source": e.get("source")},
    ),
    MetricType.BODY_FAT: _SimpleParserSpec(
        metric_type=MetricType.BODY_FAT,
        data_key="fat",
        unit="%",
        value_key="fat",
        ts_from_date_time_keys=True,
    ),
    # ── Active Zone Minutes (nested with metadata) ────────
    MetricType.ACTIVE_ZONE_MINUTES: _SimpleParserSpec(
        metric_type=MetricType.ACTIVE_ZONE_MINUTES,
        data_key="activities-active-zone-minutes",
        unit="minutes",
        value_path=("value", "activeZoneMinutes"),
        metadata_extractor=_azm_metadata,
    ),
}


# ── Specialised parser dispatch table ────────────────────────

_SPECIALISED_PARSERS: dict[
    MetricType,
    Any,  # Callable[[FitbitCollector, str, dict, str], list[SensorReading]]
] = {
    MetricType.HEART_RATE: FitbitCollector._parse_heart_rate,
    MetricType.SLEEP: FitbitCollector._parse_sleep,
    MetricType.SPO2: FitbitCollector._parse_spo2,
}
