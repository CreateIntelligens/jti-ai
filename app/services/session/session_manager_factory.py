"""
Session Manager 工廠

有 MONGODB_URI 就嘗試用 MongoDB，連不到就自動切回記憶體版本。
使用 lazy singleton，避免重複建立實例。
"""

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

HCIOT_DB_NAME = "hciot_app"

# lazy singleton cache
_singletons: dict[str, Any] = {}


def _get_or_create(
    key: str,
    mongo_factory,
    fallback_factory=None,
    label: str = "",
) -> Any:
    """通用 lazy singleton 工廠。

    嘗試用 mongo_factory 建立實例（需要 MONGODB_URI），
    失敗則用 fallback_factory（若有提供），否則回傳 None。
    """
    if key in _singletons:
        return _singletons[key]

    if os.getenv("MONGODB_URI"):
        try:
            instance = mongo_factory()
            _singletons[key] = instance
            logger.debug("Using MongoDB %s", label)
            return instance
        except Exception as e:
            fallback_desc = "falling back to in-memory" if fallback_factory else "disabled"
            logger.warning("MongoDB %s failed, %s: %s", label, fallback_desc, e)

    if fallback_factory:
        instance = fallback_factory()
        _singletons[key] = instance
        logger.info("Using in-memory/file-based %s", label)
        return instance

    return None


def get_session_manager():
    from .mongo_session_manager import MongoSessionManager
    from .session_manager import SessionManager
    return _get_or_create(
        "session_manager",
        mongo_factory=MongoSessionManager,
        fallback_factory=SessionManager,
        label="SessionManager",
    )


def get_conversation_logger():
    from app.services.logging.mongo_conversation_logger import MongoConversationLogger
    from app.services.logging.conversation_logger import ConversationLogger
    return _get_or_create(
        "conversation_logger",
        mongo_factory=MongoConversationLogger,
        fallback_factory=ConversationLogger,
        label="ConversationLogger",
    )


def get_hciot_session_manager():
    """取得 HCIoT 專用 SessionManager (hciot_app database)"""
    from .mongo_session_manager import MongoSessionManager
    from .session_manager import SessionManager
    return _get_or_create(
        "hciot_session_manager",
        mongo_factory=lambda: MongoSessionManager(db_name=HCIOT_DB_NAME),
        fallback_factory=SessionManager,
        label=f"SessionManager for HCIoT (db={HCIOT_DB_NAME})",
    )


def get_hciot_conversation_logger():
    """取得 HCIoT 專用 ConversationLogger (hciot_app database)"""
    from app.services.logging.mongo_conversation_logger import MongoConversationLogger
    from app.services.logging.conversation_logger import ConversationLogger
    return _get_or_create(
        "hciot_conversation_logger",
        mongo_factory=lambda: MongoConversationLogger(db_name=HCIOT_DB_NAME),
        fallback_factory=ConversationLogger,
        label=f"ConversationLogger for HCIoT (db={HCIOT_DB_NAME})",
    )


def get_general_chat_session_manager():
    """取得一般知識庫 Chat Session Manager（無 fallback，失敗回傳 None）"""
    from app.services.session.general_chat_session_manager import GeneralChatSessionManager
    return _get_or_create(
        "general_chat_session_manager",
        mongo_factory=GeneralChatSessionManager,
        label="GeneralChatSessionManager",
    )
