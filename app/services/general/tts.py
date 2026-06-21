"""Shared TTS configuration and job-manager factory for managed apps."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from app.services.tts_jobs import TtsJobManager


@dataclass(frozen=True)
class ManagedTtsConfig:
    app: str
    character_env: str
    default_character: str


MANAGED_TTS_CONFIGS: dict[str, ManagedTtsConfig] = {
    "jti": ManagedTtsConfig(
        app="jti",
        character_env="JTI_TTS_CHARACTER",
        default_character="hayley",
    ),
    "hciot": ManagedTtsConfig(
        app="hciot",
        character_env="HCIOT_TTS_CHARACTER",
        default_character="healthy2",
    ),
}


@lru_cache(maxsize=None)
def get_tts_job_manager(app: str, env_var: str, default_char: str) -> TtsJobManager:
    """Return the process-wide manager for an exact managed-app configuration."""
    character = (os.getenv(env_var, default_char).split(",")[0]).strip() or default_char
    return TtsJobManager(character=character, api_replacement=app)


def get_managed_tts_job_manager(app: str) -> TtsJobManager:
    """Resolve a registered managed app to its cached TTS manager."""
    config = MANAGED_TTS_CONFIGS[app]
    return get_tts_job_manager(
        config.app,
        config.character_env,
        config.default_character,
    )
