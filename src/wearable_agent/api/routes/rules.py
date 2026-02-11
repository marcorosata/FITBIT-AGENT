"""Monitoring rules CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from wearable_agent.api.schemas import RuleRequest
from wearable_agent.models import MonitoringRule

router = APIRouter(tags=["rules"])


@router.get("/rules")
async def list_rules():
    from wearable_agent.api.server import _rule_engine

    if _rule_engine is None:
        return []
    return [r.model_dump() for r in _rule_engine.list_rules()]


@router.post("/rules", status_code=201)
async def add_rule(req: RuleRequest):
    from wearable_agent.api.server import _rule_engine

    if _rule_engine is None:
        raise HTTPException(503, "Rule engine not ready.")
    rule = MonitoringRule(
        metric_type=req.metric_type,
        condition=req.condition,
        severity=req.severity,
        message_template=req.message_template,
    )
    _rule_engine.add_rule(rule)
    return {"rule_id": rule.rule_id}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    from wearable_agent.api.server import _rule_engine

    if _rule_engine is None:
        raise HTTPException(503, "Rule engine not ready.")
    removed = _rule_engine.remove_rule(rule_id)
    if not removed:
        raise HTTPException(404, "Rule not found.")
    return {"removed": True}
