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

        self.uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
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
        db = self.get_client()["jti_app"]

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

        # ===== knowledge_files 集合 =====
        if "knowledge_files" not in db.list_collection_names():
            db.create_collection("knowledge_files")
            logger.info("Created 'knowledge_files' collection")

        knowledge_files = db["knowledge_files"]

        try:
            migrated = knowledge_files.update_many(
                {"namespace": {"$exists": False}},
                {"$set": {"namespace": "jti"}},
            )
            if migrated.modified_count:
                logger.info(
                    "Backfilled namespace='jti' for %s legacy knowledge files",
                    migrated.modified_count,
                )
        except Exception as e:
            logger.warning(f"Legacy knowledge namespace backfill failed: {e}")

        try:
            legacy_index_keys = [("language", 1), ("filename", 1)]
            for idx_name, meta in list(knowledge_files.index_information().items()):
                if idx_name == "_id_":
                    continue
                if meta.get("key") == legacy_index_keys:
                    try:
                        knowledge_files.drop_index(idx_name)
                    except Exception:
                        pass

            knowledge_files.create_index(
                [("namespace", 1), ("language", 1), ("filename", 1)],
                unique=True,
            )
            knowledge_files.create_index([("namespace", 1), ("language", 1)])
            knowledge_files.create_index("language")
            logger.info("Created indexes for 'knowledge_files' collection")
        except Exception as e:
            logger.warning(f"Index creation for 'knowledge_files': {e}")

        # ===== quiz_bank_questions 集合 =====
        quiz_bank_questions = db["quiz_bank_questions"]
        try:
            # Drop legacy single-bank indexes if they exist
            for idx_name in list(quiz_bank_questions.index_information().keys()):
                if idx_name != "_id_" and "bank_id" not in idx_name:
                    try:
                        quiz_bank_questions.drop_index(idx_name)
                    except Exception:
                        pass
            quiz_bank_questions.create_index(
                [("language", 1), ("bank_id", 1), ("id", 1)], unique=True
            )
            quiz_bank_questions.create_index([("language", 1), ("bank_id", 1)])
            logger.info("Created indexes for 'quiz_bank_questions' collection")
        except Exception as e:
            logger.warning(f"Index creation for 'quiz_bank_questions': {e}")

        # ===== quiz_bank_metadata 集合 =====
        quiz_bank_metadata = db["quiz_bank_metadata"]
        try:
            # Drop legacy single-bank indexes if they exist
            for idx_name in list(quiz_bank_metadata.index_information().keys()):
                if idx_name != "_id_" and "bank_id" not in idx_name:
                    try:
                        quiz_bank_metadata.drop_index(idx_name)
                    except Exception:
                        pass
            quiz_bank_metadata.create_index(
                [("language", 1), ("bank_id", 1)], unique=True
            )
            quiz_bank_metadata.create_index("language")
            logger.info("Created indexes for 'quiz_bank_metadata' collection")
        except Exception as e:
            logger.warning(f"Index creation for 'quiz_bank_metadata': {e}")

        # ===== quiz_results 集合 =====
        quiz_results_col = db["quiz_results"]
        try:
            # Drop legacy quiz-result indexes without set_id if they exist.
            try:
                quiz_results_col.drop_index("language_1_color_id_1")
            except Exception:
                pass
            try:
                quiz_results_col.drop_index("language_1_quiz_id_1")
            except Exception:
                pass
            quiz_results_col.create_index(
                [("language", 1), ("set_id", 1), ("quiz_id", 1)], unique=True
            )
            quiz_results_col.create_index("language")
            logger.info("Created indexes for 'quiz_results' collection")
        except Exception as e:
            logger.warning(f"Index creation for 'quiz_results': {e}")

    def get_client(self) -> MongoClient:
        """取得 MongoDB 客戶端"""
        if self._client is None:
            self.connect()
        return self._client

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


_initialized_dbs: set = set()


def get_mongo_db(db_name: str):
    """便利函數：取得資料庫實例。必須明確指定 db_name（如 'jti_app' 或 'hciot_app'）。"""
    client = get_mongo_client()
    db = client.get_client()[db_name]
    if db_name not in _initialized_dbs:
        _initialized_dbs.add(db_name)
        _ensure_base_indexes(db, db_name)
    return db


def _ensure_base_indexes(db, db_name: str) -> None:
    """為非預設 database 建立基本的 sessions/conversations 索引"""
    try:
        sessions = db["sessions"]
        sessions.create_index("session_id", unique=True)
        sessions.create_index("language")
        sessions.create_index([("created_at", -1)])

        conversations = db["conversations"]
        conversations.create_index([("session_id", 1), ("turn_number", 1)])
        conversations.create_index([("mode", 1), ("timestamp", -1)])
        conversations.create_index([("timestamp", -1)])

        logger.info("Ensured base indexes for database '%s'", db_name)
    except Exception as e:
        logger.warning("Index creation for '%s' failed: %s", db_name, e)
