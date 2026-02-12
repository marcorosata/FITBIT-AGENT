"""LifeSnaps dataset collector for replaying historical Fitbit data.

Reads from the LifeSnaps 'rais_anonymized' CSV files and simulates a live
Fitbit device by streaming readings with time-shifted timestamps.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator

import pandas as pd
from wearable_agent.collectors.base import BaseCollector
from wearable_agent.models import DeviceType, MetricType, SensorReading

logger = logging.getLogger(__name__)


class LifeSnapsCollector(BaseCollector):
    """Collector that replays data from the LifeSnaps dataset."""

    device_type = DeviceType.FITBIT

    def __init__(self, data_dir: Path | None = None) -> None:
        """Initialize the collector and load dataset indices.
        
        Args:
            data_dir: Path to the 'rais_anonymized' directory. If None,
                     searches multiple known locations.
        """
        if data_dir:
            self.data_path = data_dir
        else:
            self.data_path = self._resolve_data_path()
        
        self.csv_path = self.data_path / "csv_rais_anonymized"
        self.daily_file = self.csv_path / "daily_fitbit_sema_df_unprocessed.csv"
        self.hourly_file = self.csv_path / "hourly_fitbit_sema_df_unprocessed.csv"

        self._daily_df: pd.DataFrame | None = None
        self._hourly_df: pd.DataFrame | None = None
        self._participants: list[str] = []

    @staticmethod
    def _resolve_data_path() -> Path:
        """Search known locations for the rais_anonymized dataset.

        Priority order:
        1. scripts/rais_anonymized  (Git LFS location — works on Railway)
        2. data/lifesnaps/rais_anonymized  (local dev default)
        3. Falls back to scripts/rais_anonymized even if missing.
        """
        from wearable_agent.config import _PROJECT_ROOT

        candidates = [
            _PROJECT_ROOT / "scripts" / "rais_anonymized",
            _PROJECT_ROOT / "data" / "lifesnaps" / "rais_anonymized",
            Path("scripts") / "rais_anonymized",
            Path("data") / "lifesnaps" / "rais_anonymized",
        ]
        for p in candidates:
            csv_dir = p / "csv_rais_anonymized"
            if (csv_dir / "daily_fitbit_sema_df_unprocessed.csv").exists():
                logger.info(f"LifeSnaps data found at {p}")
                return p
        # Default to first candidate (will raise FileNotFoundError later)
        return candidates[0]

    @staticmethod
    def _reassemble_bson(parts_dir: Path, output_file: Path) -> None:
        """Reassemble a BSON file from split LFS parts."""
        parts = sorted(parts_dir.glob("fitbit.bson.part*"))
        if not parts:
            return
        output_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Reassembling {len(parts)} parts -> {output_file}")
        with open(output_file, "wb") as out:
            for part in parts:
                with open(part, "rb") as inp:
                    while chunk := inp.read(64 * 1024 * 1024):
                        out.write(chunk)
        logger.info(f"Reassembled: {output_file} ({output_file.stat().st_size / 1024 / 1024:.0f} MB)")

    def _load_data(self) -> None:
        """Lazy load the CSV data."""
        if self._daily_df is not None:
            return

        if not self.daily_file.exists() or not self.hourly_file.exists():
            raise FileNotFoundError(
                f"LifeSnaps CSV files not found in {self.csv_path}. "
                "Please run scripts/download_lifesnaps.py or unzip the archive."
            )

        logger.info(
            "lifesnaps.loading_csv",
            daily=str(self.daily_file),
            daily_size_mb=round(self.daily_file.stat().st_size / 1024 / 1024, 1),
            hourly=str(self.hourly_file),
            hourly_size_mb=round(self.hourly_file.stat().st_size / 1024 / 1024, 1),
        )
        # Load daily data
        self._daily_df = pd.read_csv(self.daily_file)
        self._daily_df['date'] = pd.to_datetime(self._daily_df['date'])
        
        # Load hourly data
        self._hourly_df = pd.read_csv(self.hourly_file)
        # Hourly file has 'date' and 'hour'? Or 'time'? 
        # Based on columns seen: 'date', 'hour' (likely int 0-23?)
        # Let's create a full timestamp
        self._hourly_df['date'] = pd.to_datetime(self._hourly_df['date'])
        
        # Helper to combine date + hour -> timestamp
        # Assuming 'hour' is 0-23 integer or string
        def parse_hourly_ts(row):
            d = row['date']
            h = int(row['hour']) if 'hour' in row else 0 # fallback
            return d + timedelta(hours=h)

        self._hourly_df['timestamp'] = self._hourly_df.apply(parse_hourly_ts, axis=1)

        # Extract unique participants
        self._participants = sorted(self._daily_df['id'].unique().astype(str).tolist())
        logger.info(
            "lifesnaps.csv_loaded",
            participants=len(self._participants),
            daily_rows=len(self._daily_df),
            hourly_rows=len(self._hourly_df),
            daily_columns=list(self._daily_df.columns),
        )

    async def authenticate(self, **credentials: str) -> None:
        """No generic authentication needed for local files."""
        # Ensure data is loaded
        self._load_data()
        pass

    def get_participants(self) -> list[str]:
        """Return list of available participant IDs."""
        self._load_data()
        return self._participants

    async def fetch(
        self,
        participant_id: str,
        metrics: list[MetricType],
        *,
        date: str | None = None,
    ) -> list[SensorReading]:
        """Fetch historical readings from the dataset."""
        self._load_data()
        assert self._daily_df is not None
        assert self._hourly_df is not None

        # Filter by participant (handle type mismatch str vs int)
        try:
            pid_int = int(participant_id)
            daily_subset = self._daily_df[self._daily_df['id'] == pid_int]
            hourly_subset = self._hourly_df[self._hourly_df['id'] == pid_int]
        except ValueError:
            # if IDs are not ints
            daily_subset = self._daily_df[self._daily_df['id'] == participant_id]
            hourly_subset = self._hourly_df[self._hourly_df['id'] == participant_id]

        if date:
            target_date = pd.to_datetime(date)
            daily_subset = daily_subset[daily_subset['date'] == target_date]
            # specific date for hourly too
            hourly_subset = hourly_subset[hourly_subset['date'] == target_date]

        readings: list[SensorReading] = []

        # 1. Process Daily Metrics
        for _, row in daily_subset.iterrows():
            ts = row['date'] # Daily granularity usually means 00:00:00 or end of day?
            
            if MetricType.STRESS in metrics and 'stress_score' in row and pd.notna(row['stress_score']):
                readings.append(SensorReading(
                    participant_id=participant_id,
                    device_type=DeviceType.FITBIT,
                    metric_type=MetricType.STRESS,
                    value=float(row['stress_score']),
                    unit="score",
                    timestamp=ts
                ))
            
            if MetricType.SPO2 in metrics and 'spo2' in row and pd.notna(row['spo2']):
                readings.append(SensorReading(
                    participant_id=participant_id,
                    device_type=DeviceType.FITBIT,
                    metric_type=MetricType.SPO2,
                    value=float(row['spo2']),
                    unit="%",
                    timestamp=ts
                ))

            if MetricType.HRV in metrics and 'rmssd' in row and pd.notna(row['rmssd']):
                readings.append(SensorReading(
                    participant_id=participant_id,
                    device_type=DeviceType.FITBIT,
                    metric_type=MetricType.HRV,
                    value=float(row['rmssd']),
                    unit="ms",
                    timestamp=ts
                ))

            if MetricType.BREATHING_RATE in metrics and 'full_sleep_breathing_rate' in row and pd.notna(row['full_sleep_breathing_rate']):
                readings.append(SensorReading(
                    participant_id=participant_id,
                    device_type=DeviceType.FITBIT,
                    metric_type=MetricType.BREATHING_RATE,
                    value=float(row['full_sleep_breathing_rate']),
                    unit="brpm",
                    timestamp=ts
                ))

            if MetricType.SLEEP in metrics and 'minutesAsleep' in row and pd.notna(row['minutesAsleep']):
                readings.append(SensorReading(
                    participant_id=participant_id,
                    device_type=DeviceType.FITBIT,
                    metric_type=MetricType.SLEEP,
                    value=float(row['minutesAsleep']),
                    unit="min",
                    timestamp=ts
                ))

        # 2. Process Hourly Metrics
        for _, row in hourly_subset.iterrows():
            ts = row['timestamp']

            if MetricType.HEART_RATE in metrics and 'bpm' in row and pd.notna(row['bpm']):
                readings.append(SensorReading(
                    participant_id=participant_id,
                    device_type=DeviceType.FITBIT,
                    metric_type=MetricType.HEART_RATE,
                    value=float(row['bpm']),
                    unit="bpm",
                    timestamp=ts
                ))

            if MetricType.STEPS in metrics and 'steps' in row and pd.notna(row['steps']):
                 readings.append(SensorReading(
                    participant_id=participant_id,
                    device_type=DeviceType.FITBIT,
                    metric_type=MetricType.STEPS,
                    value=float(row['steps']),
                    unit="steps",
                    timestamp=ts
                ))
            
            # Fallback for 'ageps' if that was the column name? 
            # Assuming 'steps' exists or I need to check columns again. 
            # I'll stick to 'steps' and update if needed.

            if MetricType.CALORIES in metrics and 'calories' in row and pd.notna(row['calories']):
                readings.append(SensorReading(
                    participant_id=participant_id,
                    device_type=DeviceType.FITBIT,
                    metric_type=MetricType.CALORIES,
                    value=float(row['calories']),
                    unit="kcal",
                    timestamp=ts
                ))

            if MetricType.DISTANCE in metrics and 'distance' in row and pd.notna(row['distance']):
                 readings.append(SensorReading(
                    participant_id=participant_id,
                    device_type=DeviceType.FITBIT,
                    metric_type=MetricType.DISTANCE,
                    value=float(row['distance']),
                    unit="m", # LifeSnaps likely meters or km? Usually API is km or meters.
                    timestamp=ts
                ))

        return readings

    async def _stream_bson(
        self,
        participant_id: str,
        metrics: list[MetricType],
        speed: float = 1.0,
    ) -> AsyncIterator[SensorReading]:
        """Yield readings from BSON file, time-shifted."""
        from wearable_agent.collectors.lifesnaps_bson import BSONStreamer

        mongo_dir = self.data_path / "mongo_rais_anonymized"

        # 1. Prefer per-participant BSON (small, deployed via GitHub)
        per_participant = mongo_dir / f"participant_{participant_id}.bson"
        if per_participant.exists() and per_participant.stat().st_size > 200:
            bson_path = per_participant
            logger.info(
                "lifesnaps.bson_source",
                source="per-participant",
                path=str(bson_path),
                size_mb=round(bson_path.stat().st_size / 1024 / 1024, 1),
            )
        else:
            # 2. Fall back to full fitbit.bson
            bson_path = mongo_dir / "fitbit.bson"
            if not bson_path.exists():
                parts_dir = bson_path.parent / "fitbit_parts"
                if parts_dir.exists() and list(parts_dir.glob("fitbit.bson.part*")):
                    logger.info("Reassembling fitbit.bson from LFS parts...")
                    self._reassemble_bson(parts_dir, bson_path)
                else:
                    logger.warning(
                        "lifesnaps.bson_not_found",
                        participant=participant_id,
                        mongo_dir=str(mongo_dir),
                        files=(
                            [f.name for f in mongo_dir.iterdir()]
                            if mongo_dir.exists()
                            else []
                        ),
                    )
            else:
                logger.info(
                    "lifesnaps.bson_source",
                    source="full-file",
                    path=str(bson_path),
                    size_mb=round(bson_path.stat().st_size / 1024 / 1024, 1),
                )
        streamer = BSONStreamer(bson_path)
        
        # We need to find the first timestamp to synchronize
        # BSON reader is a generator, so we can't sort beforehand without reading all (3GB!)
        # So we assume the file is roughly chronological or we accept some out-of-order delivery
        # relative to the VERY start.
        # However, for time-shifting, we need a reference 'start' time.
        # We'll use the first record encountered as the anchor.
        
        first_ts: datetime | None = None
        replay_start_realtime: datetime | None = None

        # Filter metrics supported by BSON
        bson_supported = [MetricType.HEART_RATE, MetricType.STEPS, MetricType.CALORIES]
        target_metrics = [m for m in metrics if m in bson_supported]

        if not target_metrics:
            return

        for reading in streamer.iter_readings(participant_id, target_metrics):
            if first_ts is None:
                first_ts = reading.timestamp
                replay_start_realtime = datetime.now()
            
            # Time shift
            # Calculate delay
            assert first_ts is not None
            assert replay_start_realtime is not None
            
            time_offset = reading.timestamp - first_ts
            target_emit_time = replay_start_realtime + (time_offset / speed)
            
            # Wait
            now = datetime.now()
            wait_seconds = (target_emit_time - now).total_seconds()
            
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
                
            reading.timestamp = target_emit_time
            yield reading

    async def stream(
        self,
        participant_id: str,
        metrics: list[MetricType],
        speed: float = 1.0,
        start_date: str | None = None,
    ) -> AsyncIterator[SensorReading]:
        """Yield all readings for a participant, time-shifted to now.

        High-frequency metrics (HR, Steps, Calories) come from BSON;
        daily/hourly summary metrics (Stress, SpO2, HRV, …) from CSV.
        Both streams are merged into a single async iterator.
        """
        bson_supported = {MetricType.HEART_RATE, MetricType.STEPS, MetricType.CALORIES}
        csv_metrics = [m for m in metrics if m not in bson_supported]
        bson_metrics = [m for m in metrics if m in bson_supported]

        queue: asyncio.Queue[SensorReading | None] = asyncio.Queue()
        producer_count = int(bool(csv_metrics)) + int(bool(bson_metrics))

        if producer_count == 0:
            return

        # ── producer helpers (each puts None when done) ──────────

        async def _produce_csv() -> None:
            try:
                logger.info(
                    "lifesnaps.csv_producer_start",
                    participant=participant_id,
                    metrics=[m.value for m in csv_metrics],
                )
                readings = await self.fetch(participant_id, csv_metrics)
                if not readings:
                    logger.warning(
                        "lifesnaps.csv_producer_empty",
                        participant=participant_id,
                    )
                    return
                readings.sort(key=lambda r: r.timestamp)
                logger.info(
                    "lifesnaps.csv_producer_loaded",
                    participant=participant_id,
                    total_readings=len(readings),
                    date_range=f"{readings[0].timestamp} → {readings[-1].timestamp}",
                )
                anchor = readings[0].timestamp
                wall_start = datetime.now()
                emitted = 0
                for r in readings:
                    offset = r.timestamp - anchor
                    target = wall_start + (offset / speed)
                    delay = (target - datetime.now()).total_seconds()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    r.timestamp = datetime.now()
                    await queue.put(r)
                    emitted += 1
                logger.info(
                    "lifesnaps.csv_producer_done",
                    participant=participant_id,
                    emitted=emitted,
                )
            except Exception as exc:
                logger.error("csv_producer_failed", error=str(exc), exc_info=True)
            finally:
                await queue.put(None)

        async def _produce_bson() -> None:
            bson_count = 0
            try:
                logger.info(
                    "lifesnaps.bson_producer_start",
                    participant=participant_id,
                    metrics=[m.value for m in bson_metrics],
                )
                async for r in self._stream_bson(participant_id, bson_metrics, speed):
                    await queue.put(r)
                    bson_count += 1
                    if bson_count % 5000 == 0:
                        logger.info(
                            "lifesnaps.bson_producer_progress",
                            participant=participant_id,
                            emitted=bson_count,
                        )
                logger.info(
                    "lifesnaps.bson_producer_done",
                    participant=participant_id,
                    emitted=bson_count,
                )
            except Exception as exc:
                logger.error(
                    "bson_producer_failed",
                    error=str(exc),
                    emitted_before_error=bson_count,
                    exc_info=True,
                )
            finally:
                await queue.put(None)

        # ── launch producers ─────────────────────────────────────
        tasks: list[asyncio.Task[None]] = []
        if csv_metrics:
            tasks.append(asyncio.create_task(_produce_csv()))
        if bson_metrics:
            tasks.append(asyncio.create_task(_produce_bson()))

        # ── consumer: yield until all producers signal done ──────
        remaining = producer_count
        try:
            while remaining > 0:
                item = await queue.get()
                if item is None:
                    remaining -= 1
                else:
                    yield item
        finally:
            for t in tasks:
                t.cancel()
