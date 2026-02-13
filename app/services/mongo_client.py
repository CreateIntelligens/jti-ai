"""
MongoDB 連接管理

職責：
1. 管理 MongoDB 連接
2. 初始化集合和索引
3. 提供連接實例
"""

import logging
import os
from typing import Optional
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

logger = logging.getLogger(__name__)


class MongoDBClient:
    """MongoDB 客戶端單例"""

    _instance: Optional["MongoDBClient"] = None
    _client: Optional[MongoClient] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化 MongoDB 連接"""
        if self._client is not None:
            return

        self.uri = os.getenv(
            "MONGODB_URI",
            "mongodb://localhost:27017/jti_app"
        )
        self.db_name = "jti_app"
        self.connect()

    def connect(self) -> None:
        """連接到 MongoDB"""
        try:
            self._client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            # 測試連接
            self._client.admin.command("ping")
            logger.info("Successfully connected to MongoDB")
            self._initialize_collections()
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def _initialize_collections(self) -> None:
        """初始化集合和索引"""
        db = self.get_db()

        # ===== sessions 集合 =====
        if "sessions" not in db.list_collection_names():
            db.create_collection("sessions")
            logger.info("Created 'sessions' collection")

        sessions = db["sessions"]

        # 創建索引
        try:
            sessions.create_index("session_id", unique=True)
            sessions.create_index("mode")
            sessions.create_index("language")
            sessions.create_index([("created_at", -1)])
            logger.info("Created indexes for 'sessions' collection")
        except Exception as e:
            logger.warning(f"Index creation for 'sessions': {e}")

        # ===== conversations 集合 =====
        if "conversations" not in db.list_collection_names():
            db.create_collection("conversations")
            logger.info("Created 'conversations' collection")

        conversations = db["conversations"]

        try:
            conversations.create_index([("session_id", 1), ("turn_number", 1)])
            conversations.create_index([("mode", 1), ("timestamp", -1)])
            conversations.create_index([("timestamp", -1)])
            logger.info("Created indexes for 'conversations' collection")
        except Exception as e:
            logger.warning(f"Index creation for 'conversations': {e}")

        # ===== quizzes 集合（可選） =====
        if "quizzes" not in db.list_collection_names():
            db.create_collection("quizzes")
            logger.info("Created 'quizzes' collection")

        quizzes = db["quizzes"]

        try:
            quizzes.create_index("session_id")
            quizzes.create_index([("completed_at", -1)])
            quizzes.create_index([("language", 1), ("completed_at", -1)])
            logger.info("Created indexes for 'quizzes' collection")
        except Exception as e:
            logger.warning(f"Index creation for 'quizzes': {e}")

    def get_client(self) -> MongoClient:
        """取得 MongoDB 客戶端"""
        if self._client is None:
            self.connect()
        return self._client

    def get_db(self):
        """取得資料庫實例"""
        return self.get_client()[self.db_name]

    def close(self) -> None:
        """關閉連接"""
        if self._client:
            self._client.close()
            self._client = None
            logger.info("MongoDB connection closed")

    def health_check(self) -> bool:
        """檢查連接狀態"""
        try:
            self.get_client().admin.command("ping")
            return True
        except Exception as e:
            logger.error(f"MongoDB health check failed: {e}")
            return False


# 全域客戶端實例
_mongo_client: Optional[MongoDBClient] = None


def get_mongo_client() -> MongoDBClient:
    """取得 MongoDB 客戶端單例"""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoDBClient()
    return _mongo_client


def get_mongo_db():
    """便利函數：取得資料庫實例"""
    return get_mongo_client().get_db()
