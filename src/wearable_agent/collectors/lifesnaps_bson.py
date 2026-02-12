"""BSON reader for LifeSnaps high-frequency data."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Generator

try:
    import bson
except ImportError:
    bson = None  # type: ignore[assignment]

from wearable_agent.models import DeviceType, MetricType, SensorReading

logger = logging.getLogger(__name__)


class BSONStreamer:
    """Streams high-frequency data from the monolithic fitbit.bson file."""

    def __init__(self, bson_path: Path) -> None:
        self.bson_path = bson_path

    def iter_readings(
        self, participant_id: str, metrics: list[MetricType]
    ) -> Generator[SensorReading, None, None]:
        """Yield sensor readings from BSON matching the filter criteria.

        This performs a linear scan of the BSON file.
        """
        if not self.bson_path.exists():
            logger.error(f"BSON file not found at {self.bson_path}")
            return

        if bson is None:
            logger.error("pymongo/bson not installed — cannot stream BSON data")
            return

        # Map MetricType to BSON 'type' string
        type_map = {}
        if MetricType.HEART_RATE in metrics:
            type_map["heart_rate"] = MetricType.HEART_RATE
        if MetricType.STEPS in metrics:
            type_map["steps"] = MetricType.STEPS
        if MetricType.CALORIES in metrics:
            type_map["calories"] = MetricType.CALORIES
        # Add others if schema confirmed

        if not type_map:
            return

        target_types = set(type_map.keys())

        try:
            with open(self.bson_path, "rb") as f:
                # Iterate over BSON documents efficiently
                for doc in bson.decode_file_iter(f):
                    doc_type = doc.get("type")
                    
                    # 1. Check if type matches
                    if doc_type not in target_types:
                        continue

                    # 2. Check if participant matches
                    # BSON 'id' field is the participant ID
                    if doc.get("id") != participant_id:
                        continue

                    # 3. Parse and yield
                    try:
                        data = doc.get("data", {})
                        if not data:
                            continue

                        # Extract timestamp (e.g., "05/24/21 00:00:01")
                        dt_str = data.get("dateTime")
                        if not dt_str:
                            continue
                        
                        # Handle potential format variations if any (saw "MM/DD/YY HH:MM:SS" in sample)
                        try:
                            # Note: naive parse, assuming local or consistent UTC
                            timestamp = datetime.strptime(dt_str, "%m/%d/%y %H:%M:%S")
                        except ValueError:
                             try:
                                timestamp = datetime.fromisoformat(dt_str)
                             except ValueError:
                                continue # Skip malformed dates

                        # Extract Value
                        val = 0.0
                        unit = ""
                        metric = type_map[doc_type]

                        if (doc_type == "heart_rate"):
                            # value is a dict: {"bpm": 67, "confidence": 1}
                            val_obj = data.get("value")
                            if isinstance(val_obj, dict):
                                val = float(val_obj.get("bpm", 0))
                            else:
                                val = float(val_obj) # fallback
                            unit = "bpm"

                        elif (doc_type == "steps"):
                            # value: "0" (string)
                            val = float(data.get("value", 0))
                            unit = "steps"
                        
                        elif (doc_type == "calories"):
                             # value: "2.62"
                             val = float(data.get("value", 0))
                             unit = "kcal"

                        yield SensorReading(
                            participant_id=participant_id,
                            device_type=DeviceType.FITBIT,
                            metric_type=metric,
                            value=val,
                            unit=unit,
                            timestamp=timestamp,
                            metadata={"source": "lifesnaps_bson"}
                        )

                    except Exception as e:
                        # Log but don't crash stream on one bad record
                        # logger.warning(f"Failed to parse BSON record: {e}")
                        continue

        except Exception as e:
            logger.error(f"Error streaming BSON: {e}")
            raise

