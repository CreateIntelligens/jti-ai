"""
Session Manager 工廠

有 MONGODB_URI 就嘗試用 MongoDB，連不到就自動切回記憶體版本。
使用 lazy singleton，避免重複建立實例。
"""

import os
import logging

logger = logging.getLogger(__name__)

_session_manager = None
_conversation_logger = None


def get_session_manager():
    global _session_manager
    if _session_manager is not None:
        return _session_manager

    if os.getenv("MONGODB_URI"):
        try:
            from app.services.mongo_session_manager import MongoSessionManager
            _session_manager = MongoSessionManager()
            logger.info("Using MongoDB SessionManager")
            return _session_manager
        except Exception as e:
            logger.warning(f"MongoDB SessionManager failed, falling back to in-memory: {e}")

    from app.services.session_manager import SessionManager
    _session_manager = SessionManager()
    logger.info("Using in-memory SessionManager")
    return _session_manager


def get_conversation_logger():
    global _conversation_logger
    if _conversation_logger is not None:
        return _conversation_logger

    if os.getenv("MONGODB_URI"):
        try:
            from app.services.mongo_conversation_logger import MongoConversationLogger
            _conversation_logger = MongoConversationLogger()
            logger.info("Using MongoDB ConversationLogger")
            return _conversation_logger
        except Exception as e:
            logger.warning(f"MongoDB ConversationLogger failed, falling back to file-based: {e}")

    from app.services.conversation_logger import ConversationLogger
    _conversation_logger = ConversationLogger()
    logger.info("Using file-based ConversationLogger")
    return _conversation_logger
