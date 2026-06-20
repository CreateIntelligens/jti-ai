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

from app.services.db_names import JTI_DB_NAME

logger = logging.getLogger(__name__)


# 啟動時解析一次的有效連線字串，全程序共用，確保所有 client 連同一個目標
# （避免部分 client 連主庫、部分連備援庫造成資料分裂）。
_resolved_uri: Optional[str] = None

# 是否正運行在 Atlas 備援庫上（主庫啟動時連不到而 fallback）。
# 安全意義：同步腳本只 upsert 不刪除，Atlas 鏡像可能落後主庫的「撤權」
# （停用帳號 / 撤銷 API key / 刪帳號）。降級期間這些撤銷可能尚未生效，
# 等同 fail-open 風險窗口，必須讓營運端可察覺（見 is_using_fallback / /health）。
_using_fallback: bool = False


def is_using_fallback() -> bool:
    """是否正運行在備援庫（Atlas）上。供 /health 等對外標示降級狀態。"""
    return _using_fallback

# 啟動時試連主庫的逾時（一次性開機判斷，非執行中查詢逾時）。
# 寫死而非走 env：DocumentDB 經 db-tunnel 還要 TLS 握手，冷啟動疊加時 5s 偏緊，
# 誤判會掉 Atlas 備援且需人工合資料，代價高；開機多等幾秒無感，故給寬。
MONGODB_PROBE_TIMEOUT_MS = 10000

# 執行中查詢逾時：tunnel 卡住（後端隧道斷但 port 仍 listen）時，若不設 socket
# 逾時，查詢會無限 hang 拖垮整個服務。設積極逾時讓查詢「快速失敗」而非卡死。
# serverSelectionTimeoutMS 只管「選到 server」，選到後的讀寫須靠 socketTimeoutMS。
MONGODB_SERVER_SELECTION_TIMEOUT_MS = 5000
MONGODB_CONNECT_TIMEOUT_MS = 5000
MONGODB_SOCKET_TIMEOUT_MS = 10000


def _remember_mongodb_uri(uri: str) -> str:
    global _resolved_uri
    _resolved_uri = uri
    return uri


def _probe_mongodb_uri(uri: str, timeout_ms: int) -> tuple[bool, Exception | None]:
    probe = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
    try:
        probe.admin.command("ping")
        return True, None
    except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
        return False, exc
    finally:
        probe.close()


def resolve_mongodb_uri(mongodb_uri: str | None = None) -> str:
    """取得明確指定的 MongoDB URI，或啟動時決定要連主庫/備援庫。

    策略（一次性，非執行中動態切換）：
    0. 呼叫端若明確傳入 mongodb_uri，直接使用，不參與全域快取。
    1. 試連 MONGODB_URI（主，通常為 DocumentDB，經 db-tunnel）。
    2. 連得到 → 用主庫。
    3. 連不到，且有設定 MONGODB_URI_FALLBACK（Atlas）→ fallback 用備援庫，
       讓服務在跳板/主庫長時間不可用時仍能啟動運作。
    4. 連不到也無備援 → 回主庫字串（沿用既有行為，由上層處理連線錯誤）。

    注意：結果在程序啟動時固定。主庫之後恢復需重啟程序才會切回；
    fallback 期間寫入備援庫，需事後人工合併回主庫（限只增型資料）。
    """
    if mongodb_uri:
        return mongodb_uri
    if _resolved_uri is not None:
        return _resolved_uri

    primary = os.getenv("MONGODB_URI")
    fallback = os.getenv("MONGODB_URI_FALLBACK")

    if not primary:
        if fallback:
            logger.warning("未設定 MONGODB_URI，直接使用 MONGODB_URI_FALLBACK")
            return _remember_mongodb_uri(fallback)
        raise ValueError("未設定 MONGODB_URI")

    if not fallback:
        # 無備援設定：維持原行為，不做試連，交由實際連線時報錯。
        return _remember_mongodb_uri(primary)

    # 有備援：啟動時試連主庫一次，決定用哪個。
    primary_available, reason = _probe_mongodb_uri(primary, MONGODB_PROBE_TIMEOUT_MS)
    if primary_available:
        logger.info("主資料庫 (MONGODB_URI) 連線正常，使用主庫")
        return _remember_mongodb_uri(primary)

    global _using_fallback
    _using_fallback = True
    logger.critical(
        "⚠ 資料庫降級：主庫無法連線，已 fallback 至備援庫 (Atlas)。"
        "安全注意：備援鏡像可能落後主庫的撤權（停用帳號 / 撤銷 API key / 刪帳號），"
        "降級期間這些撤銷可能尚未生效（fail-open 風險）。請儘速修復主庫並重啟切回。"
        "原因: %s",
        reason,
    )
    return _remember_mongodb_uri(fallback)


def _ensure_session_indexes(sessions, *, include_mode: bool = False) -> None:
    sessions.create_index("session_id", unique=True)
    if include_mode:
        sessions.create_index("mode")
    sessions.create_index("language")
    sessions.create_index([("created_at", -1)])
    # 動態 TTL：依各 session 文件自帶的 expires_at 過期。
    # expireAfterSeconds=0 表示「到 expires_at 指定的時間點即過期」。
    sessions.create_index("expires_at", expireAfterSeconds=0)


def _ensure_conversation_indexes(conversations) -> None:
    conversations.create_index([("session_id", 1), ("turn_number", 1)])
    conversations.create_index([("mode", 1), ("timestamp", -1)])
    conversations.create_index([("timestamp", -1)])
    # general 等以 store 區分知識庫的對話，可直接依 store_name 查詢「某店對話」。
    # 稀疏索引：jti/hciot 的 conversation 無此欄位，不佔索引空間。
    conversations.create_index("store_name", sparse=True)


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

        self.uri = resolve_mongodb_uri()
        self.connect()

    def connect(self) -> None:
        """連接到 MongoDB"""
        try:
            self._client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=MONGODB_SERVER_SELECTION_TIMEOUT_MS,
                connectTimeoutMS=MONGODB_CONNECT_TIMEOUT_MS,
                socketTimeoutMS=MONGODB_SOCKET_TIMEOUT_MS,
            )
            # 測試連接
            self._client.admin.command("ping")
            logger.info("Successfully connected to MongoDB")
            self._initialize_collections()
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def _initialize_collections(self) -> None:
        """初始化集合和索引"""
        db = self.get_client()[JTI_DB_NAME]
        collections_ready: list[str] = []

        # ===== sessions 集合 =====
        if "sessions" not in db.list_collection_names():
            db.create_collection("sessions")

        sessions = db["sessions"]

        # 創建索引
        try:
            _ensure_session_indexes(sessions, include_mode=True)
            collections_ready.append("sessions")
        except Exception as e:
            logger.warning(f"Index creation for 'sessions': {e}")

        # ===== conversations 集合 =====
        if "conversations" not in db.list_collection_names():
            db.create_collection("conversations")

        conversations = db["conversations"]

        try:
            _ensure_conversation_indexes(conversations)
            collections_ready.append("conversations")
        except Exception as e:
            logger.warning(f"Index creation for 'conversations': {e}")

        # ===== knowledge_files 集合 =====
        if "knowledge_files" not in db.list_collection_names():
            db.create_collection("knowledge_files")

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
            collections_ready.append("knowledge_files")
        except Exception as e:
            logger.warning(f"Index creation for 'knowledge_files': {e}")

        # ===== quiz_bank_questions 集合 =====
        # Unique keys MUST include store_name: quiz banks are multi-store
        # (JTI uses __jti__, general stores use hashed ids). A key without
        # store_name makes two stores collide on the same bank_id/id.
        quiz_bank_questions = db["quiz_bank_questions"]
        try:
            for idx_name in list(quiz_bank_questions.index_information().keys()):
                # Drop legacy uniques that lack store_name (e.g. the old
                # language_1_bank_id_1_id_1). Keep store_name-scoped indexes.
                if idx_name != "_id_" and "store_name" not in idx_name:
                    try:
                        quiz_bank_questions.drop_index(idx_name)
                    except Exception:
                        pass
            quiz_bank_questions.create_index(
                [("store_name", 1), ("language", 1), ("bank_id", 1), ("id", 1)],
                unique=True,
            )
            quiz_bank_questions.create_index([("store_name", 1), ("language", 1), ("bank_id", 1)])
            collections_ready.append("quiz_bank_questions")
        except Exception as e:
            logger.warning(f"Index creation for 'quiz_bank_questions': {e}")

        # ===== quiz_bank_metadata 集合 =====
        quiz_bank_metadata = db["quiz_bank_metadata"]
        try:
            for idx_name in list(quiz_bank_metadata.index_information().keys()):
                if idx_name != "_id_" and "store_name" not in idx_name:
                    try:
                        quiz_bank_metadata.drop_index(idx_name)
                    except Exception:
                        pass
            quiz_bank_metadata.create_index(
                [("store_name", 1), ("language", 1), ("bank_id", 1)], unique=True
            )
            quiz_bank_metadata.create_index("language")
            collections_ready.append("quiz_bank_metadata")
        except Exception as e:
            logger.warning(f"Index creation for 'quiz_bank_metadata': {e}")

        # ===== quiz_results 集合 =====
        quiz_results_col = db["quiz_results"]
        try:
            for idx_name in list(quiz_results_col.index_information().keys()):
                if idx_name != "_id_" and "store_name" not in idx_name and "language" in idx_name:
                    try:
                        quiz_results_col.drop_index(idx_name)
                    except Exception:
                        pass
            quiz_results_col.create_index(
                [("store_name", 1), ("language", 1), ("set_id", 1), ("quiz_id", 1)],
                unique=True,
            )
            quiz_results_col.create_index("language")
            collections_ready.append("quiz_results")
        except Exception as e:
            logger.warning(f"Index creation for 'quiz_results': {e}")

        logger.debug("MongoDB indexes ready (%d/%d): %s", len(collections_ready), 6, ", ".join(collections_ready))

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
    """取得數據面資料庫實例，並確保 sessions/conversations 基礎索引。"""
    db = get_raw_mongo_db(db_name)
    if db_name not in _initialized_dbs:
        _initialized_dbs.add(db_name)
        _ensure_base_indexes(db, db_name)
    return db


def get_raw_mongo_db(db_name: str):
    """取得資料庫實例，不建立 data-plane sessions/conversations 索引。"""
    return get_mongo_client().get_client()[db_name]


def _ensure_base_indexes(db, db_name: str) -> None:
    """為數據面 database 建立基本的 sessions/conversations 索引。"""
    try:
        _ensure_session_indexes(db["sessions"])
        _ensure_conversation_indexes(db["conversations"])

        logger.debug("Ensured base indexes for database '%s'", db_name)
    except Exception as e:
        logger.warning("Index creation for '%s' failed: %s", db_name, e)
