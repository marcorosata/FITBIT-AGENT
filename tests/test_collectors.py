"""Tests for data models and collector registry."""

import pytest

from wearable_agent.collectors.registry import available_devices, get_collector
from wearable_agent.models import DeviceType, MetricType, SensorReading


class TestModels:
    def test_sensor_reading_defaults(self):
        reading = SensorReading(
            participant_id="P001",
            device_type=DeviceType.FITBIT,
            metric_type=MetricType.HEART_RATE,
            value=72.0,
        )
        assert reading.id  # auto-generated UUID
        assert reading.timestamp is not None
        assert reading.unit == ""

    def test_sensor_reading_with_metadata(self):
        reading = SensorReading(
            participant_id="P002",
            device_type=DeviceType.APPLE_WATCH,
            metric_type=MetricType.STEPS,
            value=5000.0,
            unit="steps",
            metadata={"source": "healthkit"},
        )
        assert reading.metadata["source"] == "healthkit"


class TestCollectorRegistry:
    def test_fitbit_available(self):
        assert DeviceType.FITBIT in available_devices()

    def test_get_fitbit_collector(self):
        collector = get_collector(DeviceType.FITBIT)
        assert collector.device_type == DeviceType.FITBIT

    def test_unknown_device_raises(self):
        with pytest.raises(ValueError, match="No collector registered"):
            get_collector(DeviceType.GARMIN)
