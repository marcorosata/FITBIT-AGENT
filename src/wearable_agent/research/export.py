"""Data export utilities for reproducible research workflows."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Sequence

import structlog

from wearable_agent.models import MetricType
from wearable_agent.storage.database import SensorReadingRow
from wearable_agent.storage.repository import ReadingRepository

logger = structlog.get_logger(__name__)


async def export_readings_csv(
    participant_id: str,
    metric_type: MetricType,
    start: datetime,
    end: datetime,
    output_path: str | Path,
    *,
    repo: ReadingRepository | None = None,
) -> Path:
    """Export sensor readings to a CSV file.

    Returns the resolved output path.
    """
    repo = repo or ReadingRepository()
    rows = await repo.get_range(participant_id, metric_type, start, end)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "participant_id", "device_type", "metric_type",
                         "value", "unit", "timestamp"])
        for r in rows:
            writer.writerow([
                r.id, r.participant_id, r.device_type, r.metric_type,
                r.value, r.unit, r.timestamp.isoformat(),
            ])

    logger.info("export.csv_written", path=str(output), rows=len(rows))
    return output


async def export_readings_json(
    participant_id: str,
    metric_type: MetricType,
    start: datetime,
    end: datetime,
    output_path: str | Path,
    *,
    repo: ReadingRepository | None = None,
) -> Path:
    """Export sensor readings to a JSON file."""
    repo = repo or ReadingRepository()
    rows = await repo.get_range(participant_id, metric_type, start, end)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    records = [
        {
            "id": r.id,
            "participant_id": r.participant_id,
            "device_type": r.device_type,
            "metric_type": r.metric_type,
            "value": r.value,
            "unit": r.unit,
            "timestamp": r.timestamp.isoformat(),
        }
        for r in rows
    ]

    with output.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    logger.info("export.json_written", path=str(output), rows=len(records))
    return output
