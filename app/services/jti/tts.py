"""JTI-specific TTS formatting and job manager wiring."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from app.services.tts_jobs import TtsJobManager
from app.services.tts_text import prepare_tts_text


def to_jti_tts_text(text: Optional[str], language: str) -> Optional[str]:
    """Prepare JTI TTS text for zh responses."""
    return prepare_tts_text(text, language, convert_digits=True)


@lru_cache(maxsize=1)
def get_jti_tts_job_manager() -> TtsJobManager:
    return TtsJobManager(
        character=os.getenv("JTI_TTS_CHARACTER", "hayley"),
        api_replacement="jti",
    )
