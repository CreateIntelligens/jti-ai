"""HCIoT-specific TTS formatting and job manager wiring."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from app.services.tts_jobs import TtsJobManager
from app.services.tts_text import prepare_tts_text


def to_hciot_tts_text(text: Optional[str], language: str) -> Optional[str]:
    """Prepare HCIoT TTS text for zh responses."""
    return prepare_tts_text(text, language)


@lru_cache(maxsize=1)
def get_hciot_tts_job_manager() -> TtsJobManager:
    character = (os.getenv("HCIOT_TTS_CHARACTER", "healthy2").split(",")[0]).strip() or "healthy2"
    return TtsJobManager(
        character=character,
        api_replacement="hciot",
    )
