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
