"""Tests for the streaming pipeline."""

import asyncio
import pytest

from wearable_agent.models import DeviceType, MetricType, SensorReading
from wearable_agent.streaming.pipeline import StreamPipeline


@pytest.mark.asyncio
async def test_pipeline_publish_and_consume():
    """Readings published to the pipeline reach registered consumers."""
    received: list[SensorReading] = []

    async def consumer(reading: SensorReading) -> None:
        received.append(reading)

    pipeline = StreamPipeline()
    pipeline.add_consumer(consumer)

    # Start pipeline in background
    task = asyncio.create_task(pipeline.start())

    reading = SensorReading(
        participant_id="P001",
        device_type=DeviceType.FITBIT,
        metric_type=MetricType.HEART_RATE,
        value=80.0,
        unit="bpm",
    )
    await pipeline.publish(reading)

    # Give the consumer loop time to process
    await asyncio.sleep(0.2)
    await pipeline.stop()
    task.cancel()

    assert len(received) == 1
    assert received[0].value == 80.0


@pytest.mark.asyncio
async def test_pipeline_batch():
    received: list[SensorReading] = []

    async def consumer(reading: SensorReading) -> None:
        received.append(reading)

    pipeline = StreamPipeline()
    pipeline.add_consumer(consumer)
    task = asyncio.create_task(pipeline.start())

    readings = [
        SensorReading(
            participant_id="P001",
            device_type=DeviceType.FITBIT,
            metric_type=MetricType.HEART_RATE,
            value=float(70 + i),
            unit="bpm",
        )
        for i in range(5)
    ]
    await pipeline.publish_batch(readings)

    await asyncio.sleep(0.5)
    await pipeline.stop()
    task.cancel()

    assert len(received) == 5
