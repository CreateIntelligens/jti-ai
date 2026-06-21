"""
Session Manager 工廠

有 MONGODB_URI 就嘗試用 MongoDB，連不到就自動切回記憶體版本。
使用 lazy singleton，避免重複建立實例。
"""

import os
import logging
from typing import Any

from app.services.db_names import ESG_DB_NAME, GENERAL_DB_NAME, HCIOT_DB_NAME, JTI_DB_NAME

logger = logging.getLogger(__name__)

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


def get_jti_session_manager():
    from .mongo_session_manager import MongoSessionManager
    from .session_manager import SessionManager
    return _get_or_create(
        "session_manager",
        mongo_factory=lambda: MongoSessionManager(db_name=JTI_DB_NAME),
        fallback_factory=SessionManager,
        label="SessionManager",
    )


def get_jti_conversation_logger():
    from app.services.logging.mongo_conversation_logger import MongoConversationLogger
    from app.services.logging.conversation_logger import ConversationLogger
    return _get_or_create(
        "conversation_logger",
        mongo_factory=lambda: MongoConversationLogger(db_name=JTI_DB_NAME),
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


def get_esg_session_manager():
    """取得 ESG 專用 SessionManager (esg_app database)。"""
    from .mongo_session_manager import MongoSessionManager
    from .session_manager import SessionManager

    return _get_or_create(
        "esg_session_manager",
        mongo_factory=lambda: MongoSessionManager(db_name=ESG_DB_NAME),
        fallback_factory=SessionManager,
        label=f"SessionManager for ESG (db={ESG_DB_NAME})",
    )


def get_esg_conversation_logger():
    """取得 ESG 專用 ConversationLogger (esg_app database)。"""
    from app.services.logging.conversation_logger import ConversationLogger
    from app.services.logging.mongo_conversation_logger import MongoConversationLogger

    return _get_or_create(
        "esg_conversation_logger",
        mongo_factory=lambda: MongoConversationLogger(db_name=ESG_DB_NAME),
        fallback_factory=ConversationLogger,
        label=f"ConversationLogger for ESG (db={ESG_DB_NAME})",
    )


def get_general_chat_session_manager():
    """取得一般知識庫 Chat Session Manager（general_app database）

    Uses the standard MongoSessionManager (same as JTI/HCIoT) with an
    in-memory SessionManager fallback so the General agent can operate
    in environments without MongoDB (tests, local dev).

    使用獨立的 general_app 庫，不再寄生於 jti_app（避免 general 對話狀態與
    JTI 測驗 session 混在同一集合）。
    """
    from .mongo_session_manager import MongoSessionManager
    from .session_manager import SessionManager
    return _get_or_create(
        "general_chat_session_manager",
        mongo_factory=lambda: MongoSessionManager(db_name=GENERAL_DB_NAME),
        fallback_factory=SessionManager,
        label=f"GeneralChatSessionManager (db={GENERAL_DB_NAME})",
    )


def get_general_conversation_logger():
    """取得一般知識庫專用 ConversationLogger（general_app database）。

    過去 general 借用 get_jti_conversation_logger() 把對話寫進 jti_app，
    現拆出獨立 logger 指向 general_app，與 session 同庫。
    """
    from app.services.logging.mongo_conversation_logger import MongoConversationLogger
    from app.services.logging.conversation_logger import ConversationLogger
    return _get_or_create(
        "general_conversation_logger",
        mongo_factory=lambda: MongoConversationLogger(db_name=GENERAL_DB_NAME),
        fallback_factory=ConversationLogger,
        label=f"ConversationLogger for General (db={GENERAL_DB_NAME})",
    )
