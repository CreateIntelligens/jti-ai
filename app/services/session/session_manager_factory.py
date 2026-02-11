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
            from .mongo_session_manager import MongoSessionManager
            _session_manager = MongoSessionManager()
            logger.info("Using MongoDB SessionManager")
            return _session_manager
        except Exception as e:
            logger.warning(f"MongoDB SessionManager failed, falling back to in-memory: {e}")

    from .session_manager import SessionManager
    _session_manager = SessionManager()
    logger.info("Using in-memory SessionManager")
    return _session_manager


def get_conversation_logger():
    global _conversation_logger
    if _conversation_logger is not None:
        return _conversation_logger

    if os.getenv("MONGODB_URI"):
        try:
            from app.services.logging.mongo_conversation_logger import MongoConversationLogger
            _conversation_logger = MongoConversationLogger()
            logger.info("Using MongoDB ConversationLogger")
            return _conversation_logger
        except Exception as e:
            logger.warning(f"MongoDB ConversationLogger failed, falling back to file-based: {e}")

    from app.services.logging.conversation_logger import ConversationLogger
    _conversation_logger = ConversationLogger()
    logger.info("Using file-based ConversationLogger")
    return _conversation_logger


_general_chat_session_manager = None


def get_general_chat_session_manager():
    """取得一般知識庫 Chat Session Manager"""
    global _general_chat_session_manager
    if _general_chat_session_manager is not None:
        return _general_chat_session_manager

    if os.getenv("MONGODB_URI"):
        try:
            from app.services.session.general_chat_session_manager import GeneralChatSessionManager
            _general_chat_session_manager = GeneralChatSessionManager()
            print("[Factory] ✅ 使用 MongoDB GeneralChatSessionManager")
            return _general_chat_session_manager
        except Exception as e:
            print(f"[Factory] ⚠️ MongoDB GeneralChatSessionManager 失敗: {e}，停用 session 持久化")

    return None
