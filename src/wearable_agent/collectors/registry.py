"""Collector registry — discover and instantiate device collectors by type."""

from __future__ import annotations

from typing import Type

from wearable_agent.collectors.base import BaseCollector
from wearable_agent.collectors.fitbit import FitbitCollector
from wearable_agent.models import DeviceType

# ── Registry ──────────────────────────────────────────────────

_REGISTRY: dict[DeviceType, Type[BaseCollector]] = {
    DeviceType.FITBIT: FitbitCollector,
}


def register_collector(device_type: DeviceType, cls: Type[BaseCollector]) -> None:
    """Register a new collector class for a device type."""
    _REGISTRY[device_type] = cls


def get_collector(device_type: DeviceType) -> BaseCollector:
    """Instantiate and return a collector for the given device type.

    Raises :class:`ValueError` if no collector is registered.
    """
    cls = _REGISTRY.get(device_type)
    if cls is None:
        raise ValueError(
            f"No collector registered for {device_type.value}. "
            f"Available: {[d.value for d in _REGISTRY]}"
        )
    return cls()


def available_devices() -> list[DeviceType]:
    """Return device types that have a registered collector."""
    return list(_REGISTRY.keys())
