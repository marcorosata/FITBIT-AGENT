"""Abstract base class for all wearable data collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from wearable_agent.models import DeviceType, MetricType, SensorReading


class BaseCollector(ABC):
    """Contract that every device-specific collector must implement.

    A collector is responsible for authenticating with a wearable device API,
    fetching sensor data, and yielding normalised :class:`SensorReading`
    objects.
    """

    device_type: DeviceType

    @abstractmethod
    async def authenticate(self, **credentials: str) -> None:
        """Establish an authenticated session with the device API."""

    @abstractmethod
    async def fetch(
        self,
        participant_id: str,
        metrics: list[MetricType],
        *,
        date: str | None = None,
    ) -> list[SensorReading]:
        """Fetch a batch of readings for the given participant and metrics.

        Parameters
        ----------
        participant_id:
            Unique study participant identifier.
        metrics:
            Which metric types to retrieve.
        date:
            ISO-format date string (``YYYY-MM-DD``).  ``None`` means *today*.
        """

    async def stream(
        self,
        participant_id: str,
        metrics: list[MetricType],
    ) -> AsyncIterator[SensorReading]:
        """Yield readings as they become available (pull-based streaming).

        The default implementation simply wraps :meth:`fetch`.  Device
        collectors that support real-time push can override this.
        """
        readings = await self.fetch(participant_id, metrics)
        for r in readings:
            yield r

    async def close(self) -> None:
        """Release any resources held by the collector."""
