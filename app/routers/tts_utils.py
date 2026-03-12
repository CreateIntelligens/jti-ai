"""
Shared TTS helpers and endpoint factory.

Centralises emoji stripping, TTS job queuing, and the GET/POST TTS
endpoints that are identical across JTI and HCIoT routers.
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.auth import verify_auth
from app.schemas.chat import ChatResponse
from app.services.jti.tts_jobs import tts_job_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Emoji regex & helpers
# ---------------------------------------------------------------------------

_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f9ff"   # miscellaneous symbols, emoticons, supplemental
    "\U0001fa00-\U0001faff"   # symbols extended-A
    "\U00002600-\U000027bf"   # misc symbols & dingbats
    "\U0000fe00-\U0000fe0f"   # variation selectors
    "\U0000200d"              # zero width joiner
    "\U000023cf-\U000023fa"   # misc technical
    "\U00002b50-\U00002b55"   # stars
    "]+",
    flags=re.UNICODE,
)


def strip_emoji(text: str) -> str:
    """Remove emoji characters from *text*."""
    return _EMOJI_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# TTS job helpers
# ---------------------------------------------------------------------------

def queue_tts_generation(tts_text: Optional[str], language: str) -> Optional[str]:
    """Submit *tts_text* for background TTS generation; return the job id."""
    if not tts_text:
        return None
    try:
        return tts_job_manager.create_job(text=tts_text, language=language)
    except Exception as exc:
        logger.warning("Failed to queue TTS generation: %s", exc)
        return None


def attach_tts_message_id(response: ChatResponse, language: str) -> ChatResponse:
    """Strip emoji from display/tts text, queue TTS, and return an updated copy."""
    cleaned_message = strip_emoji(response.message)
    cleaned_tts = strip_emoji(response.tts_text) if response.tts_text else response.tts_text
    tts_message_id = queue_tts_generation(cleaned_tts, language)
    return response.model_copy(update={
        "message": cleaned_message,
        "tts_text": cleaned_tts,
        "tts_message_id": tts_message_id,
    })


# ---------------------------------------------------------------------------
# Pydantic model shared by POST /tts endpoints
# ---------------------------------------------------------------------------

class TtsCreateRequest(BaseModel):
    text: str = Field(..., description="Text content for TTS generation")
    language: str = Field("zh", description="Language code, e.g. zh or en")


# ---------------------------------------------------------------------------
# Endpoint factory
# ---------------------------------------------------------------------------

def register_tts_endpoints(router: APIRouter) -> None:
    """Mount GET ``/tts/{tts_message_id}`` and POST ``/tts`` on *router*."""

    @router.get("/tts/{tts_message_id}")
    async def get_tts_audio(tts_message_id: str, auth: dict = Depends(verify_auth)):
        """Get pre-generated TTS audio by message id."""
        job = tts_job_manager.get_job(tts_message_id)
        if not job:
            raise HTTPException(status_code=404, detail="TTS audio not found")

        status = job.get("status")
        if status == "pending":
            return JSONResponse(status_code=202, content={"status": "pending"})
        if status == "failed":
            raise HTTPException(status_code=500, detail=job.get("error") or "TTS generation failed")

        audio_bytes = job.get("audio_bytes")
        if not isinstance(audio_bytes, (bytes, bytearray)) or not audio_bytes:
            raise HTTPException(status_code=500, detail="TTS audio is unavailable")

        content_type = job.get("content_type")
        if not isinstance(content_type, str) or not content_type.strip():
            content_type = "audio/mpeg"

        return Response(
            content=audio_bytes,
            media_type=content_type,
            headers={"Cache-Control": "private, max-age=300"},
        )

    @router.post("/tts")
    async def create_tts_audio(request: TtsCreateRequest, auth: dict = Depends(verify_auth)):
        """Create a new background TTS job and return its message id."""
        text = (request.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="TTS text is empty")

        language = (request.language or "zh").strip().lower() or "zh"
        tts_message_id = queue_tts_generation(text, language)
        if not tts_message_id:
            raise HTTPException(status_code=500, detail="Failed to queue TTS generation")

        return {"tts_message_id": tts_message_id}
