"""Analysis helpers — pandas-based utilities for research workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from wearable_agent.models import MetricType
from wearable_agent.storage.repository import ReadingRepository


async def readings_to_dataframe(
    participant_id: str,
    metric_type: MetricType,
    start: datetime,
    end: datetime,
    *,
    repo: ReadingRepository | None = None,
) -> pd.DataFrame:
    """Load sensor readings into a :class:`pandas.DataFrame`.

    Columns: ``timestamp``, ``value``, ``unit``, ``device_type``.
    The ``timestamp`` column is set as the index for easy time-series work.
    """
    repo = repo or ReadingRepository()
    rows = await repo.get_range(participant_id, metric_type, start, end)

    records = [
        {
            "timestamp": r.timestamp,
            "value": r.value,
            "unit": r.unit,
            "device_type": r.device_type,
        }
        for r in rows
    ]
    df = pd.DataFrame(records)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
    return df


def compute_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Return summary statistics for a time-series DataFrame.

    Expects a ``value`` column.
    """
    if df.empty or "value" not in df.columns:
        return {"count": 0}

    return {
        "count": int(df["value"].count()),
        "mean": round(float(df["value"].mean()), 2),
        "std": round(float(df["value"].std()), 2),
        "min": float(df["value"].min()),
        "max": float(df["value"].max()),
        "median": float(df["value"].median()),
        "q25": float(df["value"].quantile(0.25)),
        "q75": float(df["value"].quantile(0.75)),
    }


def resample_readings(df: pd.DataFrame, rule: str = "5min") -> pd.DataFrame:
    """Resample a readings DataFrame to a coarser time resolution.

    Parameters
    ----------
    df:
        DataFrame with a ``DatetimeIndex`` and ``value`` column.
    rule:
        Pandas offset alias (``'1min'``, ``'5min'``, ``'1h'``, etc.).
    """
    if df.empty:
        return df
    return df.resample(rule).agg(
        value_mean=("value", "mean"),
        value_min=("value", "min"),
        value_max=("value", "max"),
        count=("value", "count"),
    )
