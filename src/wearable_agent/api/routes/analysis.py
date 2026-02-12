"""Agent analysis routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from wearable_agent.api.schemas import AnalyseRequest

router = APIRouter(tags=["agent"])


@router.post("/analyse")
async def analyse(req: AnalyseRequest):
    """Send a free-form question to the LLM agent."""
    from wearable_agent.api.server import _agent

    if _agent is None:
        raise HTTPException(503, "Agent not ready.")
    result = await _agent.analyse(req.query)
    return {"response": result}


@router.post("/analyse/metric")
async def analyse_metric(
    participant_id: str = Query(..., description="Participant ID"),
    metric: str = Query(..., description="Metric name (hrv, stress, etc.)"),
    hours: int = Query(24, ge=1, le=168, description="Hours of history"),
):
    """Ask the agent to perform a deep analysis of a specific metric.

    The agent fetches the data, computes statistics, detects trends and
    anomalies, and returns a human-readable interpretation.
    """
    from wearable_agent.api.server import _agent

    if _agent is None:
        raise HTTPException(503, "Agent not ready.")

    query = (
        f"Analyse the **{metric}** data for participant {participant_id} "
        f"over the last {hours} hours.  "
        f"Use the analyse_metric tool to fetch the data, then provide: "
        f"1) A summary of the statistics, 2) Whether values are within "
        f"normal ranges, 3) Trend direction, 4) Any anomalies found, "
        f"5) Actionable recommendations.  Be concise but thorough."
    )
    result = await _agent.analyse(query)
    return {"metric": metric, "participant_id": participant_id, "analysis": result}


@router.get("/evaluate/{participant_id}")
async def evaluate_participant(
    participant_id: str,
    metric: str = Query("heart_rate"),
    hours: int = Query(24, ge=1, le=168),
):
    """Ask the agent for a structured evaluation of a participant."""
    from wearable_agent.api.server import _agent

    if _agent is None:
        raise HTTPException(503, "Agent not ready.")
    result = await _agent.evaluate_participant(participant_id, metric, hours)
    return {"evaluation": result}
