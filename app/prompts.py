"""
Prompt 管理模組 (MongoDB 版本)
每個 Store 可以有多個 Prompt (最多3個)
"""

import os
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.server_api import ServerApi

from .core import log


class Prompt(BaseModel):
    """單個 Prompt 模型"""
    id: str = Field(default_factory=lambda: f"prompt_{uuid.uuid4().hex[:8]}")
    name: str
    content: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class StorePrompts(BaseModel):
    """Store 的所有 Prompts"""
    store_name: str
    prompts: List[Prompt] = Field(default_factory=list)
    active_prompt_id: Optional[str] = None


class PromptManager:
    """Prompt 管理器 (MongoDB 版本)"""

    MAX_PROMPTS_PER_STORE = 3
    DB_NAME = "gemini_notebook"
    COLLECTION_NAME = "prompts"

    def __init__(self, mongodb_uri: str = None):
        """初始化 Prompt Manager

        Args:
            mongodb_uri: MongoDB 連線字串，預設從環境變數取得
        """
        uri = mongodb_uri or os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError("未設定 MONGODB_URI")

        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[self.DB_NAME]
        self.collection = self.db[self.COLLECTION_NAME]

        # 建立索引
        self.collection.create_index("store_name", unique=True)

        log(f"[PromptManager] 已連接 MongoDB: {self.DB_NAME}.{self.COLLECTION_NAME}")

    def _load_store_prompts(self, store_name: str) -> StorePrompts:
        """載入 Store 的 prompts"""
        doc = self.collection.find_one({"store_name": store_name})

        if not doc:
            return StorePrompts(store_name=store_name)

        # 移除 MongoDB 的 _id 欄位
        doc.pop("_id", None)
        return StorePrompts(**doc)

    def _save_store_prompts(self, store_prompts: StorePrompts):
        """保存 Store 的 prompts"""
        data = store_prompts.model_dump()

        self.collection.update_one(
            {"store_name": store_prompts.store_name},
            {"$set": data},
            upsert=True
        )

    def list_prompts(self, store_name: str) -> List[Prompt]:
        """列出 Store 的所有 prompts"""
        store_prompts = self._load_store_prompts(store_name)
        return store_prompts.prompts

    def get_prompt(self, store_name: str, prompt_id: str) -> Optional[Prompt]:
        """取得特定 prompt"""
        store_prompts = self._load_store_prompts(store_name)

        for prompt in store_prompts.prompts:
            if prompt.id == prompt_id:
                return prompt

        return None

    def get_active_prompt(self, store_name: str) -> Optional[Prompt]:
        """取得當前啟用的 prompt"""
        store_prompts = self._load_store_prompts(store_name)

        if not store_prompts.active_prompt_id:
            return None

        return self.get_prompt(store_name, store_prompts.active_prompt_id)

    def create_prompt(self, store_name: str, name: str, content: str) -> Prompt:
        """建立新的 prompt

        Args:
            store_name: Store 名稱
            name: Prompt 名稱
            content: Prompt 內容

        Returns:
            新建立的 Prompt

        Raises:
            ValueError: 超過最大數量限制
        """
        store_prompts = self._load_store_prompts(store_name)

        # 檢查數量限制
        if len(store_prompts.prompts) >= self.MAX_PROMPTS_PER_STORE:
            raise ValueError(f"每個 Store 最多只能有 {self.MAX_PROMPTS_PER_STORE} 個 Prompts")

        # 建立新 prompt
        new_prompt = Prompt(name=name, content=content)
        store_prompts.prompts.append(new_prompt)

        # 如果是第一個 prompt，自動設為啟用
        if len(store_prompts.prompts) == 1:
            store_prompts.active_prompt_id = new_prompt.id

        self._save_store_prompts(store_prompts)
        log(f"[PromptManager] 建立 Prompt: {name} (store: {store_name})")

        return new_prompt

    def update_prompt(self, store_name: str, prompt_id: str, name: Optional[str] = None,
                     content: Optional[str] = None) -> Prompt:
        """更新 prompt

        Args:
            store_name: Store 名稱
            prompt_id: Prompt ID
            name: 新名稱（可選）
            content: 新內容（可選）

        Returns:
            更新後的 Prompt

        Raises:
            ValueError: Prompt 不存在
        """
        store_prompts = self._load_store_prompts(store_name)

        for i, prompt in enumerate(store_prompts.prompts):
            if prompt.id == prompt_id:
                if name is not None:
                    prompt.name = name
                if content is not None:
                    prompt.content = content
                prompt.updated_at = datetime.utcnow().isoformat()

                store_prompts.prompts[i] = prompt
                self._save_store_prompts(store_prompts)
                log(f"[PromptManager] 更新 Prompt: {prompt_id}")

                return prompt

        raise ValueError(f"Prompt {prompt_id} 不存在")

    def delete_prompt(self, store_name: str, prompt_id: str):
        """刪除 prompt

        Args:
            store_name: Store 名稱
            prompt_id: Prompt ID

        Raises:
            ValueError: Prompt 不存在
        """
        store_prompts = self._load_store_prompts(store_name)

        # 找到並刪除 prompt
        original_length = len(store_prompts.prompts)
        store_prompts.prompts = [p for p in store_prompts.prompts if p.id != prompt_id]

        if len(store_prompts.prompts) == original_length:
            raise ValueError(f"Prompt {prompt_id} 不存在")

        # 如果刪除的是啟用中的 prompt，清除 active_prompt_id
        if store_prompts.active_prompt_id == prompt_id:
            store_prompts.active_prompt_id = (
                store_prompts.prompts[0].id if store_prompts.prompts else None
            )

        self._save_store_prompts(store_prompts)
        log(f"[PromptManager] 刪除 Prompt: {prompt_id}")

    def set_active_prompt(self, store_name: str, prompt_id: str):
        """設定啟用的 prompt

        Args:
            store_name: Store 名稱
            prompt_id: Prompt ID

        Raises:
            ValueError: Prompt 不存在
        """
        store_prompts = self._load_store_prompts(store_name)

        # 檢查 prompt 是否存在
        if not any(p.id == prompt_id for p in store_prompts.prompts):
            raise ValueError(f"Prompt {prompt_id} 不存在")

        store_prompts.active_prompt_id = prompt_id
        self._save_store_prompts(store_prompts)
        log(f"[PromptManager] 設定啟用 Prompt: {prompt_id}")

    def clear_active_prompt(self, store_name: str):
        """取消啟用的 prompt（不使用任何 prompt）"""
        store_prompts = self._load_store_prompts(store_name)
        store_prompts.active_prompt_id = None
        self._save_store_prompts(store_prompts)
        log(f"[PromptManager] 取消啟用 Prompt: {store_name}")

    def delete_store_prompts(self, store_name: str):
        """刪除整個 Store 的 prompts"""
        result = self.collection.delete_one({"store_name": store_name})
        if result.deleted_count > 0:
            log(f"[PromptManager] 刪除 Store prompts: {store_name}")
