"""Data-access layer — thin async wrappers around SQLAlchemy queries."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from wearable_agent.affect.models import (
    AffectiveState,
    Confidence,
    EMALabel,
    FeatureWindow,
    InferenceOutput,
    ParticipantBaseline,
    QualityFlags,
)
from wearable_agent.models import Alert, MetricType, SensorReading
from wearable_agent.storage.database import (
    AlertRow,
    EMALabelRow,
    FeatureWindowRow,
    InferenceOutputRow,
    OAuthTokenRow,
    ParticipantBaselineRow,
    ParticipantRow,
    SensorReadingRow,
    get_session_factory,
)


class BaseRepository:
    """Shared base with session management for all repositories."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._external_session = session

    async def _session(self) -> AsyncSession:
        if self._external_session is not None:
            return self._external_session
        return get_session_factory()()


class ReadingRepository(BaseRepository):
    """CRUD operations for :class:`SensorReading` objects."""

    # ── Write ─────────────────────────────────────────────────

    async def save(self, reading: SensorReading) -> None:
        session = await self._session()
        row = SensorReadingRow(
            id=reading.id,
            participant_id=reading.participant_id,
            device_type=reading.device_type.value,
            metric_type=reading.metric_type.value,
            value=reading.value,
            unit=reading.unit,
            timestamp=reading.timestamp,
            metadata_json=json.dumps(reading.metadata),
        )
        session.add(row)
        await session.commit()

    async def save_batch(self, readings: list[SensorReading]) -> int:
        session = await self._session()
        rows = [
            SensorReadingRow(
                id=r.id,
                participant_id=r.participant_id,
                device_type=r.device_type.value,
                metric_type=r.metric_type.value,
                value=r.value,
                unit=r.unit,
                timestamp=r.timestamp,
                metadata_json=json.dumps(r.metadata),
            )
            for r in readings
        ]
        session.add_all(rows)
        await session.commit()
        return len(rows)

    # ── Read ──────────────────────────────────────────────────

    async def count_for_participant(self, participant_id: str) -> int:
        """Count total readings stored for a participant."""
        session = await self._session()
        stmt = (
            select(func.count())
            .select_from(SensorReadingRow)
            .where(SensorReadingRow.participant_id == participant_id)
        )
        result = await session.execute(stmt)
        return result.scalar() or 0

    async def delete_for_participant(self, participant_id: str) -> int:
        """Delete all readings for a participant. Returns count deleted."""
        from sqlalchemy import delete as sa_delete

        session = await self._session()
        # Count first
        count = await self.count_for_participant(participant_id)
        stmt = sa_delete(SensorReadingRow).where(
            SensorReadingRow.participant_id == participant_id
        )
        await session.execute(stmt)
        await session.commit()
        return count

    async def get_latest(
        self,
        participant_id: str,
        metric_type: MetricType,
        limit: int = 1,
    ) -> Sequence[SensorReadingRow]:
        session = await self._session()
        stmt = (
            select(SensorReadingRow)
            .where(
                SensorReadingRow.participant_id == participant_id,
                SensorReadingRow.metric_type == metric_type.value,
            )
            .order_by(SensorReadingRow.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_latest_by_source(
        self,
        participant_id: str,
        metric_type: MetricType,
        data_source: str,
        limit: int = 1,
    ) -> Sequence[SensorReadingRow]:
        """Get latest readings filtered by data source (dataset or live)."""
        session = await self._session()
        # Filter by metadata JSON containing source field
        # Note: SQLite JSON functions may be limited, using LIKE for now
        stmt = (
            select(SensorReadingRow)
            .where(
                SensorReadingRow.participant_id == participant_id,
                SensorReadingRow.metric_type == metric_type.value,
                SensorReadingRow.metadata_json.like(f'%"source": "{data_source}"%'),
            )
            .order_by(SensorReadingRow.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_range(
        self,
        participant_id: str,
        metric_type: MetricType,
        start: datetime,
        end: datetime,
    ) -> Sequence[SensorReadingRow]:
        session = await self._session()
        stmt = (
            select(SensorReadingRow)
            .where(
                SensorReadingRow.participant_id == participant_id,
                SensorReadingRow.metric_type == metric_type.value,
                SensorReadingRow.timestamp >= start,
                SensorReadingRow.timestamp <= end,
            )
            .order_by(SensorReadingRow.timestamp.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()


class AlertRepository(BaseRepository):
    """CRUD operations for :class:`Alert` objects."""

    async def save(self, alert: Alert) -> None:
        session = await self._session()
        row = AlertRow(
            id=alert.id,
            participant_id=alert.participant_id,
            metric_type=alert.metric_type.value,
            severity=alert.severity.value,
            message=alert.message,
            value=alert.value,
            threshold_low=alert.threshold_low,
            threshold_high=alert.threshold_high,
            timestamp=alert.timestamp,
        )
        session.add(row)
        await session.commit()

    async def get_by_participant(
        self, participant_id: str, limit: int = 50
    ) -> Sequence[AlertRow]:
        session = await self._session()
        stmt = (
            select(AlertRow)
            .where(AlertRow.participant_id == participant_id)
            .order_by(AlertRow.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()


# ── Affect inference repositories ─────────────────────────────


class FeatureWindowRepository(BaseRepository):
    """CRUD for :class:`FeatureWindow` aggregations."""

    async def save(self, window: FeatureWindow) -> None:
        session = await self._session()
        row = FeatureWindowRow(
            id=window.id,
            participant_id=window.participant_id,
            window_start=window.window_start,
            window_end=window.window_end,
            window_duration_seconds=window.window_duration_seconds,
            activity_context=window.activity_context.value,
            features_json=window.model_dump_json(
                exclude={"id", "participant_id", "window_start", "window_end",
                          "window_duration_seconds", "activity_context", "quality"}
            ),
            quality_json=window.quality.model_dump_json(),
        )
        session.add(row)
        await session.commit()

    async def get_latest(
        self, participant_id: str, limit: int = 1
    ) -> Sequence[FeatureWindowRow]:
        session = await self._session()
        stmt = (
            select(FeatureWindowRow)
            .where(FeatureWindowRow.participant_id == participant_id)
            .order_by(FeatureWindowRow.window_end.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_range(
        self, participant_id: str, start: datetime, end: datetime
    ) -> Sequence[FeatureWindowRow]:
        session = await self._session()
        stmt = (
            select(FeatureWindowRow)
            .where(
                FeatureWindowRow.participant_id == participant_id,
                FeatureWindowRow.window_start >= start,
                FeatureWindowRow.window_end <= end,
            )
            .order_by(FeatureWindowRow.window_start.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()


class InferenceOutputRepository(BaseRepository):
    """CRUD for :class:`InferenceOutput` results."""

    async def save(self, output: InferenceOutput) -> None:
        session = await self._session()
        row = InferenceOutputRow(
            id=output.id,
            participant_id=output.participant_id,
            timestamp=output.timestamp,
            feature_window_id=output.feature_window_id,
            activity_context=output.activity_context.value,
            arousal_score=output.state.arousal_score,
            arousal_confidence=output.state.arousal_confidence.value,
            stress_score=output.state.stress_score,
            stress_confidence=output.state.stress_confidence.value,
            valence_score=output.state.valence_score,
            valence_confidence=output.state.valence_confidence.value,
            dominant_emotion=output.state.dominant_emotion.value,
            dominant_emotion_confidence=output.state.dominant_emotion_confidence.value,
            contributing_signals_json=json.dumps(output.contributing_signals),
            explanation=output.explanation,
            top_features_json=json.dumps(output.top_features),
            quality_json=output.quality.model_dump_json(),
            model_version=output.model_version,
        )
        session.add(row)
        await session.commit()

    async def get_latest(
        self, participant_id: str, limit: int = 1
    ) -> Sequence[InferenceOutputRow]:
        session = await self._session()
        stmt = (
            select(InferenceOutputRow)
            .where(InferenceOutputRow.participant_id == participant_id)
            .order_by(InferenceOutputRow.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_range(
        self, participant_id: str, start: datetime, end: datetime
    ) -> Sequence[InferenceOutputRow]:
        session = await self._session()
        stmt = (
            select(InferenceOutputRow)
            .where(
                InferenceOutputRow.participant_id == participant_id,
                InferenceOutputRow.timestamp >= start,
                InferenceOutputRow.timestamp <= end,
            )
            .order_by(InferenceOutputRow.timestamp.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()


class EMARepository(BaseRepository):
    """CRUD for :class:`EMALabel` ground-truth entries."""

    async def save(self, label: EMALabel) -> None:
        session = await self._session()
        row = EMALabelRow(
            id=label.id,
            participant_id=label.participant_id,
            timestamp=label.timestamp,
            arousal=label.arousal,
            valence=label.valence,
            stress=label.stress,
            emotion_tag=label.emotion_tag.value if label.emotion_tag else None,
            context_note=label.context_note,
            trigger=label.trigger,
            inference_output_id=label.inference_output_id,
        )
        session.add(row)
        await session.commit()

    async def get_by_participant(
        self, participant_id: str, limit: int = 50
    ) -> Sequence[EMALabelRow]:
        session = await self._session()
        stmt = (
            select(EMALabelRow)
            .where(EMALabelRow.participant_id == participant_id)
            .order_by(EMALabelRow.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_range(
        self, participant_id: str, start: datetime, end: datetime
    ) -> Sequence[EMALabelRow]:
        session = await self._session()
        stmt = (
            select(EMALabelRow)
            .where(
                EMALabelRow.participant_id == participant_id,
                EMALabelRow.timestamp >= start,
                EMALabelRow.timestamp <= end,
            )
            .order_by(EMALabelRow.timestamp.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def count_today(self, participant_id: str) -> int:
        """Count EMA labels submitted today (for prompt scheduling)."""
        session = await self._session()
        from datetime import date

        today_start = datetime.combine(date.today(), datetime.min.time())
        stmt = (
            select(EMALabelRow)
            .where(
                EMALabelRow.participant_id == participant_id,
                EMALabelRow.timestamp >= today_start,
            )
        )
        result = await session.execute(stmt)
        return len(result.scalars().all())


class BaselineRepository(BaseRepository):
    """CRUD for :class:`ParticipantBaseline` personalised baselines."""

    async def get(self, participant_id: str) -> ParticipantBaselineRow | None:
        session = await self._session()
        stmt = select(ParticipantBaselineRow).where(
            ParticipantBaselineRow.participant_id == participant_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, baseline: ParticipantBaseline) -> None:
        session = await self._session()
        existing = await self.get(baseline.participant_id)
        if existing is None:
            row = ParticipantBaselineRow(
                participant_id=baseline.participant_id,
                updated_at=baseline.updated_at,
                hr_baseline_morning=baseline.hr_baseline_morning,
                hr_baseline_afternoon=baseline.hr_baseline_afternoon,
                hr_baseline_evening=baseline.hr_baseline_evening,
                hr_baseline_night=baseline.hr_baseline_night,
                hr_baseline_rest=baseline.hr_baseline_rest,
                hr_std_baseline=baseline.hr_std_baseline,
                hrv_rmssd_baseline=baseline.hrv_rmssd_baseline,
                hrv_rmssd_std=baseline.hrv_rmssd_std,
                br_baseline=baseline.br_baseline,
                br_std=baseline.br_std,
                skin_temp_baseline=baseline.skin_temp_baseline,
                sleep_duration_baseline=baseline.sleep_duration_baseline,
                sleep_efficiency_baseline=baseline.sleep_efficiency_baseline,
                ewma_alpha=baseline.ewma_alpha,
                observation_count=baseline.observation_count,
            )
            session.add(row)
        else:
            existing.updated_at = baseline.updated_at
            existing.hr_baseline_morning = baseline.hr_baseline_morning
            existing.hr_baseline_afternoon = baseline.hr_baseline_afternoon
            existing.hr_baseline_evening = baseline.hr_baseline_evening
            existing.hr_baseline_night = baseline.hr_baseline_night
            existing.hr_baseline_rest = baseline.hr_baseline_rest
            existing.hr_std_baseline = baseline.hr_std_baseline
            existing.hrv_rmssd_baseline = baseline.hrv_rmssd_baseline
            existing.hrv_rmssd_std = baseline.hrv_rmssd_std
            existing.br_baseline = baseline.br_baseline
            existing.br_std = baseline.br_std
            existing.skin_temp_baseline = baseline.skin_temp_baseline
            existing.sleep_duration_baseline = baseline.sleep_duration_baseline
            existing.sleep_efficiency_baseline = baseline.sleep_efficiency_baseline
            existing.ewma_alpha = baseline.ewma_alpha
            existing.observation_count = baseline.observation_count
        await session.commit()


# ── Participant & OAuth token repositories ────────────────────


class ParticipantRepository(BaseRepository):
    """CRUD operations for :class:`Participant` objects."""

    async def save(self, participant_id: str, display_name: str = "",
                   device_type: str = "fitbit", metadata_json: str = "{}") -> None:
        session = await self._session()
        existing = await self.get(participant_id)
        if existing is not None:
            existing.display_name = display_name
            existing.device_type = device_type
            existing.metadata_json = metadata_json
        else:
            row = ParticipantRow(
                participant_id=participant_id,
                display_name=display_name,
                device_type=device_type,
                metadata_json=metadata_json,
            )
            session.add(row)
        await session.commit()

    async def get(self, participant_id: str) -> ParticipantRow | None:
        session = await self._session()
        stmt = select(ParticipantRow).where(
            ParticipantRow.participant_id == participant_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, active_only: bool = True) -> Sequence[ParticipantRow]:
        session = await self._session()
        stmt = select(ParticipantRow).order_by(ParticipantRow.enrolled_at.desc())
        if active_only:
            stmt = stmt.where(ParticipantRow.active == 1)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def update_last_sync(self, participant_id: str, sync_time: datetime) -> None:
        session = await self._session()
        row = await self.get(participant_id)
        if row:
            row.last_sync = sync_time
            await session.commit()

    async def set_active(self, participant_id: str, active: bool) -> bool:
        session = await self._session()
        row = await self.get(participant_id)
        if row is None:
            return False
        row.active = 1 if active else 0
        await session.commit()
        return True

    async def delete(self, participant_id: str) -> bool:
        session = await self._session()
        row = await self.get(participant_id)
        if row is None:
            return False
        await session.delete(row)
        await session.commit()
        return True


class TokenRepository(BaseRepository):
    """CRUD operations for OAuth tokens."""

    async def upsert(
        self,
        participant_id: str,
        access_token: str,
        refresh_token: str = "",
        provider: str = "fitbit",
        expires_at: datetime | None = None,
        scopes: str = "",
    ) -> None:
        session = await self._session()
        existing = await self.get(participant_id, provider)
        if existing is not None:
            existing.access_token = access_token
            existing.refresh_token = refresh_token
            existing.expires_at = expires_at
            existing.scopes = scopes
            existing.updated_at = datetime.utcnow()
        else:
            row = OAuthTokenRow(
                participant_id=participant_id,
                provider=provider,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scopes=scopes,
            )
            session.add(row)
        await session.commit()

    async def get(self, participant_id: str, provider: str = "fitbit") -> OAuthTokenRow | None:
        session = await self._session()
        stmt = select(OAuthTokenRow).where(
            OAuthTokenRow.participant_id == participant_id,
            OAuthTokenRow.provider == provider,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, participant_id: str, provider: str = "fitbit") -> bool:
        session = await self._session()
        row = await self.get(participant_id, provider)
        if row is None:
            return False
        await session.delete(row)
        await session.commit()
        return True

    async def list_all(self, provider: str = "fitbit") -> Sequence[OAuthTokenRow]:
        session = await self._session()
        stmt = select(OAuthTokenRow).where(OAuthTokenRow.provider == provider)
        result = await session.execute(stmt)
        return result.scalars().all()
