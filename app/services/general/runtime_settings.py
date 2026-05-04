"""General KB runtime settings — follows the same pattern as JTI/HCIoT
but with no per-prompt customization initially (prompt_manager's active
prompt content is used directly as persona; no nested profile map)."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, Optional

from pydantic import BaseModel, Field

from app.services._shared.runtime_settings_base import RuleSections
from app.services.general.agent_prompts import (
    DEFAULT_MAX_RESPONSE_CHARS,
    DEFAULT_RESPONSE_RULE_SECTIONS,
)


class GeneralRuntimeSettings(BaseModel):
    response_rule_sections: Dict[str, RuleSections] = Field(
        default_factory=lambda: {
            "zh": RuleSections(**DEFAULT_RESPONSE_RULE_SECTIONS["zh"]),
            "en": RuleSections(**DEFAULT_RESPONSE_RULE_SECTIONS["en"]),
        }
    )
    max_response_chars: int = Field(default=DEFAULT_MAX_RESPONSE_CHARS, ge=0, le=600)


def get_default_runtime_settings() -> GeneralRuntimeSettings:
    return GeneralRuntimeSettings()


def load_runtime_settings_from_prompt_manager(
    prompt_manager,
    prompt_id: Optional[str] = None,
    store_name: Optional[str] = None,
) -> GeneralRuntimeSettings:
    """Load runtime settings.

    General KB doesn't use the nested-profile runtime settings infrastructure
    yet, so this always returns defaults.  The hook exists so GeneralAgent's
    interface matches JTI/HCIoT exactly.
    """
    return get_default_runtime_settings()
