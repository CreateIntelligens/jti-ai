"""
API Key 管理模組 (MongoDB 版本)
每個 API Key 綁定一個知識庫，可選指定 prompt_index
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from functools import lru_cache
from typing import List, Optional

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, Field
from pymongo import MongoClient

from app.services.db_names import CONTROL_PLANE_DB_NAME

logger = logging.getLogger(__name__)


def log(message: str) -> None:
    logger.info(message)


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """取得 Fernet 加密器 (用於對外 API key 明文的可逆加密)。

    金鑰來自環境變數 API_ENCRYPTION_KEY (Fernet.generate_key() 產生的
    base64 字串)。未設定則 fail-fast,不靜默降級成明文/不加密。
    """
    raw = os.getenv("API_ENCRYPTION_KEY")
    if not raw:
        raise RuntimeError(
            "未設定 API_ENCRYPTION_KEY；對外 API key 需要它做可逆加密。"
            "請以 `python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` 產生一把並設進環境變數。"
        )
    try:
        return Fernet(raw.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"API_ENCRYPTION_KEY 格式無效 (需為 Fernet 金鑰): {exc}") from exc


def _parse_iso_utc(value) -> Optional[datetime]:
    """Parse an ISO-8601 string (or pass-through datetime) into a UTC-aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _api_key_from_doc(doc: dict) -> "APIKey":
    doc.pop("_id", None)
    return APIKey(**doc)


class APIKey(BaseModel):
    """API Key 模型"""
    id: str = Field(default_factory=lambda: f"key_{secrets.token_hex(4)}")
    key_hash: str  # 存 hash，用於驗證 sk-xxx（快速、不需解密）
    key_encrypted: Optional[str] = None  # Fernet 加密後的明文，供事後 reveal/複製
    key_prefix: str  # 存前幾碼方便辨識，如 "sk-abc..."
    name: str  # 用途說明，如 "給 Cursor 用"
    store_name: str  # 綁定的知識庫
    prompt_index: Optional[int] = None  # None = 用預設, 0/1/2 = 指定
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_used_at: Optional[str] = None


class APIKeyManager:
    """API Key 管理器"""

    DB_NAME = CONTROL_PLANE_DB_NAME
    COLLECTION_NAME = "api_keys"
    KEY_PREFIX = "sk-"

    def __init__(self, mongodb_uri: str = None):
        """初始化 API Key Manager"""
        uri = mongodb_uri or os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError("未設定 MONGODB_URI")

        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[self.DB_NAME]
        self.collection = self.db[self.COLLECTION_NAME]

        # 建立索引
        self.collection.create_index("key_hash", unique=True)
        self.collection.create_index("store_name")

        log(f"[APIKeyManager] 已連接 MongoDB: {self.DB_NAME}.{self.COLLECTION_NAME}")

    @staticmethod
    def _hash_key(key: str) -> str:
        """對 API Key 進行 hash"""
        return hashlib.sha256(key.encode()).hexdigest()

    @classmethod
    def _generate_key(cls) -> str:
        """產生新的 API Key"""
        return f"{cls.KEY_PREFIX}{secrets.token_hex(24)}"

    def create_key(self, name: str, store_name: str, prompt_index: Optional[int] = None) -> tuple[APIKey, str]:
        """建立新的 API Key

        Returns:
            tuple: (APIKey 物件, 明文 key) - 明文 key 只會顯示這一次
        """
        # 產生 key
        raw_key = self._generate_key()
        key_hash = self._hash_key(raw_key)
        key_prefix = raw_key[:10] + "..."
        key_encrypted = _get_fernet().encrypt(raw_key.encode()).decode()

        # 建立記錄
        api_key = APIKey(
            key_hash=key_hash,
            key_encrypted=key_encrypted,
            key_prefix=key_prefix,
            name=name,
            store_name=store_name,
            prompt_index=prompt_index
        )

        # 存入 MongoDB
        self.collection.insert_one(api_key.model_dump())
        log(f"[APIKeyManager] 建立 API Key: {key_prefix} (store: {store_name})")

        return api_key, raw_key

    def verify_key(self, raw_key: str) -> Optional[APIKey]:
        """驗證 API Key 並返回對應資料

        Returns:
            APIKey 物件，如果無效則返回 None
        """
        if not raw_key or not raw_key.startswith(self.KEY_PREFIX):
            return None

        key_hash = self._hash_key(raw_key)
        doc = self.collection.find_one({"key_hash": key_hash})

        if not doc:
            return None

        now = datetime.now(timezone.utc)
        last_used_dt = _parse_iso_utc(doc.get("last_used_at"))
        if last_used_dt is None or (now - last_used_dt).total_seconds() >= 60:
            self.collection.update_one(
                {"key_hash": key_hash},
                {"$set": {"last_used_at": now.isoformat()}}
            )

        return _api_key_from_doc(doc)

    def list_keys(self, store_name: Optional[str] = None) -> List[APIKey]:
        """列出 API Keys

        Args:
            store_name: 可選，篩選特定知識庫的 keys
        """
        query = {"store_name": store_name} if store_name else {}
        docs = self.collection.find(query).sort("created_at", -1)

        return [_api_key_from_doc(doc) for doc in docs]

    def get_key(self, key_id: str) -> Optional[APIKey]:
        """根據 ID 取得 API Key"""
        doc = self.collection.find_one({"id": key_id})
        if not doc:
            return None

        return _api_key_from_doc(doc)

    def reveal_key(self, key_id: str) -> Optional[str]:
        """解密回傳指定 key 的明文 sk-xxx。

        Returns:
            明文 key 字串；key 不存在回 None。
            key 沒有加密欄位 (例如改版前的舊資料) 或解密失敗 → raise,
            由呼叫端轉成適當的錯誤回應。
        """
        doc = self.collection.find_one({"id": key_id})
        if not doc:
            return None

        encrypted = doc.get("key_encrypted")
        if not encrypted:
            raise ValueError("此 key 無加密明文 (可能為舊版資料)，無法還原")

        try:
            return _get_fernet().decrypt(encrypted.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("解密失敗：API_ENCRYPTION_KEY 可能已變更") from exc

    def update_key(self, key_id: str, name: Optional[str] = None,
                   prompt_index: Optional[int] = None) -> Optional[APIKey]:
        """更新 API Key 設定"""
        update_fields = {}
        if name is not None:
            update_fields["name"] = name
        if prompt_index is not None:
            update_fields["prompt_index"] = prompt_index

        if not update_fields:
            return self.get_key(key_id)

        result = self.collection.find_one_and_update(
            {"id": key_id},
            {"$set": update_fields},
            return_document=True
        )

        if not result:
            return None

        result.pop("_id", None)
        return APIKey(**result)

    def delete_key(self, key_id: str) -> bool:
        """刪除 API Key"""
        result = self.collection.delete_one({"id": key_id})
        if result.deleted_count > 0:
            log(f"[APIKeyManager] 刪除 API Key: {key_id}")
            return True
        return False

    def delete_store_keys(self, store_name: str) -> int:
        """刪除知識庫的所有 API Keys"""
        result = self.collection.delete_many({"store_name": store_name})
        if result.deleted_count > 0:
            log(f"[APIKeyManager] 刪除 Store 的所有 API Keys: {store_name} ({result.deleted_count} 個)")
        return result.deleted_count
