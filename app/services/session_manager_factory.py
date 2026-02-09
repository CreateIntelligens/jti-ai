"""
Session Manager 工廠

職責：
1. 根據環境設定選擇合適的 SessionManager 實現
2. 支持 MongoDB 和記憶體版本的無縫切換
3. 提供統一的 API
"""

import os
import logging

logger = logging.getLogger(__name__)


def get_session_manager():
    """
    工廠函數：取得合適的 SessionManager 實現

    優先級：
    1. 環境變數 USE_MONGO_SESSION（優先）
    2. 環境變數 MONGODB_URI（存在則使用 MongoDB）
    3. 預設使用記憶體版本

    Returns:
        SessionManager 實例（MongoDB 或記憶體版本）
    """
    use_mongo = os.getenv("USE_MONGO_SESSION", "").lower() in ["true", "1", "yes"]

    if use_mongo:
        try:
            from app.services.mongo_session_manager import mongo_session_manager
            logger.info("Using MongoDB SessionManager")
            return mongo_session_manager
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB SessionManager: {e}")
            logger.info("Falling back to in-memory SessionManager")
            from app.services.session_manager import session_manager
            return session_manager
    else:
        logger.info("Using in-memory SessionManager")
        from app.services.session_manager import session_manager
        return session_manager


def get_conversation_logger():
    """
    工廠函數：取得合適的 ConversationLogger 實現

    優先級：
    1. 環境變數 USE_MONGO_LOGS（優先）
    2. 環境變數 MONGODB_URI（存在則使用 MongoDB）
    3. 預設使用檔案日誌

    Returns:
        ConversationLogger 實例（MongoDB 或檔案版本）
    """
    use_mongo = os.getenv("USE_MONGO_LOGS", "").lower() in ["true", "1", "yes"]

    if use_mongo:
        try:
            from app.services.mongo_conversation_logger import mongo_conversation_logger
            logger.info("Using MongoDB ConversationLogger")
            return mongo_conversation_logger
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB ConversationLogger: {e}")
            logger.info("Falling back to file-based ConversationLogger")
            from app.services.conversation_logger import conversation_logger
            return conversation_logger
    else:
        logger.info("Using file-based ConversationLogger")
        from app.services.conversation_logger import conversation_logger
        return conversation_logger
