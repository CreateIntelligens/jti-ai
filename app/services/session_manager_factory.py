"""
Session Manager 工廠

有 MONGODB_URI 就嘗試用 MongoDB，連不到就自動切回記憶體/檔案版本
"""

import os
import logging

logger = logging.getLogger(__name__)


def get_session_manager():
    if os.getenv("MONGODB_URI"):
        try:
            from app.services.mongo_session_manager import mongo_session_manager
            logger.info("Using MongoDB SessionManager")
            return mongo_session_manager
        except Exception as e:
            logger.warning(f"MongoDB SessionManager failed, falling back to in-memory: {e}")

    from app.services.session_manager import session_manager
    logger.info("Using in-memory SessionManager")
    return session_manager


def get_conversation_logger():
    if os.getenv("MONGODB_URI"):
        try:
            from app.services.mongo_conversation_logger import mongo_conversation_logger
            logger.info("Using MongoDB ConversationLogger")
            return mongo_conversation_logger
        except Exception as e:
            logger.warning(f"MongoDB ConversationLogger failed, falling back to file-based: {e}")

    from app.services.conversation_logger import conversation_logger
    logger.info("Using file-based ConversationLogger")
    return conversation_logger
