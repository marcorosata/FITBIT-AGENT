"""Participant management API routes."""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from wearable_agent.storage.repository import ParticipantRepository, TokenRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/participants", tags=["participants"])


# ── Request / response models ────────────────────────────────


class CreateParticipantRequest(BaseModel):
    participant_id: str
    display_name: str = ""
    device_type: str = "fitbit"
    metadata: dict[str, Any] = {}


class UpdateParticipantRequest(BaseModel):
    display_name: str | None = None
    active: bool | None = None
    metadata: dict[str, Any] | None = None


# ── CRUD endpoints ────────────────────────────────────────────


@router.get("", summary="List all participants")
async def list_participants(
    active_only: bool = Query(True, description="Only return active participants"),
):
    repo = ParticipantRepository()
    rows = await repo.list_all(active_only=active_only)
    return [
        {
            "participant_id": r.participant_id,
            "display_name": r.display_name,
            "device_type": r.device_type,
            "active": bool(r.active),
            "enrolled_at": r.enrolled_at.isoformat() if r.enrolled_at else None,
            "last_sync": r.last_sync.isoformat() if r.last_sync else None,
        }
        for r in rows
    ]


@router.post("", status_code=201, summary="Register a participant")
async def create_participant(req: CreateParticipantRequest):
    repo = ParticipantRepository()
    existing = await repo.get(req.participant_id)
    if existing is not None:
        raise HTTPException(409, f"Participant {req.participant_id} already exists.")

    await repo.save(
        participant_id=req.participant_id,
        display_name=req.display_name,
        device_type=req.device_type,
        metadata_json=json.dumps(req.metadata),
    )
    logger.info("participant.created", id=req.participant_id)
    return {"participant_id": req.participant_id, "created": True}


@router.get("/{participant_id}", summary="Get participant details")
async def get_participant(participant_id: str):
    repo = ParticipantRepository()
    row = await repo.get(participant_id)
    if row is None:
        raise HTTPException(404, "Participant not found.")

    # Check token status
    token_repo = TokenRepository()
    token_row = await token_repo.get(participant_id, "fitbit")

    return {
        "participant_id": row.participant_id,
        "display_name": row.display_name,
        "device_type": row.device_type,
        "active": bool(row.active),
        "enrolled_at": row.enrolled_at.isoformat() if row.enrolled_at else None,
        "last_sync": row.last_sync.isoformat() if row.last_sync else None,
        "metadata": json.loads(row.metadata_json) if row.metadata_json else {},
        "fitbit_linked": token_row is not None,
    }


@router.patch("/{participant_id}", summary="Update participant")
async def update_participant(participant_id: str, req: UpdateParticipantRequest):
    repo = ParticipantRepository()
    row = await repo.get(participant_id)
    if row is None:
        raise HTTPException(404, "Participant not found.")

    if req.active is not None:
        await repo.set_active(participant_id, req.active)

    if req.display_name is not None or req.metadata is not None:
        await repo.save(
            participant_id=participant_id,
            display_name=req.display_name or row.display_name,
            device_type=row.device_type,
            metadata_json=json.dumps(req.metadata) if req.metadata else row.metadata_json,
        )

    return {"participant_id": participant_id, "updated": True}


@router.delete("/{participant_id}", summary="Remove a participant")
async def delete_participant(participant_id: str):
    repo = ParticipantRepository()
    removed = await repo.delete(participant_id)
    if not removed:
        raise HTTPException(404, "Participant not found.")

    # Also remove tokens
    token_repo = TokenRepository()
    await token_repo.delete(participant_id, "fitbit")

    logger.info("participant.deleted", id=participant_id)
    return {"participant_id": participant_id, "deleted": True}
