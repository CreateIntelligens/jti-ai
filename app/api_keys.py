"""
API Key 管理模組 (MongoDB 版本)
每個 API Key 綁定一個知識庫，可選指定 prompt_index
"""

import os
import secrets
import hashlib
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field
from pymongo import MongoClient

from .core import log


class APIKey(BaseModel):
    """API Key 模型"""
    id: str = Field(default_factory=lambda: f"key_{secrets.token_hex(4)}")
    key_hash: str  # 存 hash，不存明文
    key_prefix: str  # 存前幾碼方便辨識，如 "sk-abc..."
    name: str  # 用途說明，如 "給 Cursor 用"
    store_name: str  # 綁定的知識庫
    prompt_index: Optional[int] = None  # None = 用預設, 0/1/2 = 指定
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    last_used_at: Optional[str] = None


class APIKeyManager:
    """API Key 管理器"""

    DB_NAME = "gemini_notebook"
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

    @staticmethod
    def _generate_key() -> str:
        """產生新的 API Key"""
        return f"sk-{secrets.token_hex(24)}"

    def create_key(self, name: str, store_name: str, prompt_index: Optional[int] = None) -> tuple[APIKey, str]:
        """建立新的 API Key

        Returns:
            tuple: (APIKey 物件, 明文 key) - 明文 key 只會顯示這一次
        """
        # 產生 key
        raw_key = self._generate_key()
        key_hash = self._hash_key(raw_key)
        key_prefix = raw_key[:10] + "..."

        # 建立記錄
        api_key = APIKey(
            key_hash=key_hash,
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

        # 更新最後使用時間
        self.collection.update_one(
            {"key_hash": key_hash},
            {"$set": {"last_used_at": datetime.utcnow().isoformat()}}
        )

        doc.pop("_id", None)
        return APIKey(**doc)

    def list_keys(self, store_name: Optional[str] = None) -> List[APIKey]:
        """列出 API Keys

        Args:
            store_name: 可選，篩選特定知識庫的 keys
        """
        query = {"store_name": store_name} if store_name else {}
        docs = self.collection.find(query).sort("created_at", -1)

        keys = []
        for doc in docs:
            doc.pop("_id", None)
            keys.append(APIKey(**doc))

        return keys

    def get_key(self, key_id: str) -> Optional[APIKey]:
        """根據 ID 取得 API Key"""
        doc = self.collection.find_one({"id": key_id})
        if not doc:
            return None

        doc.pop("_id", None)
        return APIKey(**doc)

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
