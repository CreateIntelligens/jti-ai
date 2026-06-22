"""
Shared application state and dependency functions for routers.

All mutable globals are stored here so that routers can import them
without circular imports with main.py.
"""

import logging

from .api_keys import APIKeyManager
from .users import UserManager
from .services.general.tts import get_managed_tts_job_manager
from .services.session.session_manager_factory import (
    get_general_chat_session_manager,
    get_general_conversation_logger,
    get_esg_conversation_logger,
    get_esg_session_manager,
    get_hciot_conversation_logger,
    get_hciot_session_manager,
    get_jti_conversation_logger,
    get_jti_session_manager,
)

logger = logging.getLogger(__name__)

# --- Mutable application state (set during startup) ---
prompt_manager = None  # PromptManager
api_key_manager: APIKeyManager | None = None
user_manager: UserManager | None = None


def init_managers():
    """Called from app startup event to initialise managers."""
    global prompt_manager, api_key_manager, user_manager
    try:
        from .services import app_key_map
        from .services.gemini_clients import init_registry
        from .services.gemini_service import init_gemini_client
        init_registry()
        app_key_map.validate_app_key_map()
        init_gemini_client()

        from .prompts import PromptManager
        prompt_manager = PromptManager()
        api_key_manager = APIKeyManager()
        user_manager = UserManager()
        general_session_manager = get_general_chat_session_manager()
        get_general_conversation_logger()
        get_jti_session_manager()
        get_jti_conversation_logger()
        get_managed_tts_job_manager("jti")
        get_hciot_session_manager()
        get_hciot_conversation_logger()
        get_managed_tts_job_manager("hciot")
        get_esg_session_manager()
        get_esg_conversation_logger()
        get_managed_tts_job_manager("esg")
        get_managed_tts_job_manager("general")

        # === Module-specific startup hooks ===
        from .services.jti.startup import jti_startup
        jti_startup(prompt_manager)

        from .services.hciot.startup import hciot_startup
        hciot_startup()

        storage = "MongoDB" if general_session_manager else "in-memory"
        logger.info("[Startup] Managers ready (storage=%s)", storage)
    except ValueError as e:
        logger.warning("[Startup] %s", e)
