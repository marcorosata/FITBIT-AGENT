"""Media upload routes — audio / video linked to participants."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import structlog
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from wearable_agent.config import _PROJECT_ROOT

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/media", tags=["media"])

# Persistent media directory (on Railway it lives under /tmp)
_MEDIA_DIR = Path("/tmp/data/media") if Path("/tmp/data").exists() else (_PROJECT_ROOT / "data" / "media")
_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Allowed extensions
_AUDIO_EXT = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".aac", ".flac"}
_VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
_ALLOWED_EXT = _AUDIO_EXT | _VIDEO_EXT

# Simple in-memory registry (in production you'd persist to DB)
_media_index: list[dict] = []


def _classify(ext: str) -> str:
    if ext in _AUDIO_EXT:
        return "audio"
    if ext in _VIDEO_EXT:
        return "video"
    return "unknown"


@router.post("/upload", status_code=201)
async def upload_media(
    file: UploadFile = File(...),
    participant_id: str = Form(...),
    label: str = Form(""),
    notes: str = Form(""),
):
    """Upload an audio or video file and link it to a participant.

    The file is stored on disk under ``data/media/<participant_id>/``.
    Metadata is kept in an in-memory index returned by ``GET /media``.
    """
    if not file.filename:
        raise HTTPException(400, "No filename provided.")

    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_EXT)}",
        )

    media_type = _classify(ext)
    file_id = uuid.uuid4().hex[:12]
    safe_name = f"{file_id}{ext}"
    dest_dir = _MEDIA_DIR / participant_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_name

    contents = await file.read()
    dest_path.write_bytes(contents)
    size_kb = len(contents) / 1024

    entry = {
        "id": file_id,
        "participant_id": participant_id,
        "filename": file.filename,
        "stored_as": safe_name,
        "media_type": media_type,
        "extension": ext,
        "size_kb": round(size_kb, 1),
        "label": label or file.filename,
        "notes": notes,
        "uploaded_at": datetime.utcnow().isoformat(),
    }
    _media_index.append(entry)

    logger.info(
        "media.uploaded",
        id=file_id,
        participant=participant_id,
        type=media_type,
        size_kb=round(size_kb, 1),
    )
    return entry


@router.get("")
async def list_media(participant_id: str | None = None):
    """List all uploaded media, optionally filtered by participant."""
    if participant_id:
        return [m for m in _media_index if m["participant_id"] == participant_id]
    return _media_index


@router.delete("/{media_id}")
async def delete_media(media_id: str):
    """Delete a media entry and its file from disk."""
    entry = next((m for m in _media_index if m["id"] == media_id), None)
    if not entry:
        raise HTTPException(404, "Media not found.")

    file_path = _MEDIA_DIR / entry["participant_id"] / entry["stored_as"]
    if file_path.exists():
        file_path.unlink()

    _media_index.remove(entry)
    logger.info("media.deleted", id=media_id)
    return {"deleted": media_id}


@router.post("/voice-chat", status_code=200)
async def voice_chat(
    file: UploadFile = File(...),
    participant_id: str = Form(""),
):
    """Receive a voice recording, transcribe it via OpenAI Whisper,
    then pass the transcript to the agent for analysis.

    Returns both the transcript and the agent's response.
    """
    import openai

    from wearable_agent.api.server import _agent
    from wearable_agent.config import get_settings

    if _agent is None:
        raise HTTPException(503, "Agent not ready.")

    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(503, "OpenAI API key not configured (needed for transcription).")

    # Save temp file for Whisper
    ext = Path(file.filename or "voice.webm").suffix.lower()
    if ext not in _AUDIO_EXT:
        ext = ".webm"
    tmp_path = _MEDIA_DIR / f"_voice_{uuid.uuid4().hex[:8]}{ext}"
    contents = await file.read()
    tmp_path.write_bytes(contents)

    try:
        client = openai.OpenAI(api_key=settings.openai_api_key)
        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        transcript = transcription.text.strip()
        logger.info("voice_chat.transcribed", chars=len(transcript))

        if not transcript:
            return {"transcript": "", "response": "I couldn't understand the audio. Please try again."}

        # Pass to agent
        if participant_id:
            query = f"[Voice from participant {participant_id}]: {transcript}"
        else:
            query = transcript

        response = await _agent.analyse(query)
        return {"transcript": transcript, "response": response}

    finally:
        # Clean up temp file
        if tmp_path.exists():
            tmp_path.unlink()
