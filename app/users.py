"""
使用者管理模組 (MongoDB 版本)
三層 RBAC: super_admin / admin / user
- super_admin / admin: app 為 None
- user: 綁定單一 app / key 範圍,或綁定單一 store_name
密碼僅存 bcrypt 雜湊,不存明文。
"""

import logging
import os
import secrets
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from pymongo import MongoClient

from app.security.passwords import hash_password, verify_password

logger = logging.getLogger(__name__)


# 允許的角色集合
ALLOWED_ROLES = {"super_admin", "admin", "user"}


class User(BaseModel):
    """使用者模型"""
    id: str = Field(default_factory=lambda: f"user_{secrets.token_hex(4)}")
    username: str
    password_hash: str  # 存 bcrypt 雜湊,不存明文
    role: str  # super_admin / admin / user
    app: str | None = None  # app 或 key 範圍,如 hciot/jti/general/key_name:POC1;僅 role=user 有意義
    store_name: str | None = None
    created_by: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    disabled: bool = False


class UserManager:
    """使用者管理器"""

    DB_NAME = "gemini_notebook"
    COLLECTION_NAME = "users"

    def __init__(self, mongodb_uri: str | None = None):
        """初始化 User Manager"""
        uri = mongodb_uri or os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError("未設定 MONGODB_URI")

        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[self.DB_NAME]
        self.collection = self.db[self.COLLECTION_NAME]

        # 建立索引: username 唯一
        self.collection.create_index("username", unique=True)

        logger.info(
            "[UserManager] 已連接 MongoDB: %s.%s",
            self.DB_NAME,
            self.COLLECTION_NAME,
        )

    @staticmethod
    def _validate_role_scope(
        role: str,
        app: str | None,
        store_name: str | None = None,
    ) -> None:
        """驗證角色與可存取範圍;不合法則丟 ValueError。

        - role 必須在 ALLOWED_ROLES 內
        - role == "user" 必須有非空 app 或 store_name
        """
        if role not in ALLOWED_ROLES:
            raise ValueError(f"不合法的角色: {role!r} (允許: {sorted(ALLOWED_ROLES)})")
        if role == "user" and not (app or store_name):
            raise ValueError("role=user 必須指定 app 或 store_name")
        normalized_app = (app or "").strip().lower()
        if role == "user" and normalized_app.startswith("key:"):
            raise ValueError("role=user 的 key scope 必須使用 key_name:<name>")

    @staticmethod
    def _user_from_doc(doc: dict) -> User:
        payload = dict(doc)
        payload.pop("_id", None)
        return User(**payload)

    def create_user(
        self,
        username: str,
        password: str,
        role: str,
        app: str | None = None,
        store_name: str | None = None,
        created_by: str | None = None,
    ) -> User:
        """建立新使用者

        密碼以 bcrypt 雜湊後存放,絕不存明文。
        角色 / 存取範圍驗證在任何 DB 操作之前進行。
        """
        # 驗證 (在連 DB 之前)
        self._validate_role_scope(role, app, store_name)

        user = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            app=app,
            store_name=store_name,
            created_by=created_by,
        )

        self.collection.insert_one(user.model_dump())
        logger.info(
            "[UserManager] 建立使用者: %s (role: %s, app: %s)",
            username,
            role,
            app,
        )

        return user

    def verify_credentials(self, username: str, password: str) -> User | None:
        """驗證帳密

        Returns:
            User 物件 (存在、未停用、密碼正確);否則 None
        """
        doc = self.collection.find_one({"username": username})
        if not doc:
            return None

        user = self._user_from_doc(doc)
        if user.disabled:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def get_user(self, user_id: str) -> User | None:
        """根據 ID 取得使用者"""
        doc = self.collection.find_one({"id": user_id})
        if not doc:
            return None

        return self._user_from_doc(doc)

    def get_by_username(self, username: str) -> User | None:
        """根據 username 取得使用者"""
        doc = self.collection.find_one({"username": username})
        if not doc:
            return None

        return self._user_from_doc(doc)

    def list_users(
        self,
        role: str | None = None,
        app: str | None = None,
    ) -> list[User]:
        """列出使用者 (依 created_at 由新到舊)"""
        query = {}
        if role is not None:
            query["role"] = role
        if app is not None:
            query["app"] = app

        docs = self.collection.find(query).sort("created_at", -1)

        return [self._user_from_doc(doc) for doc in docs]

    def set_disabled(self, user_id: str, disabled: bool) -> bool:
        """啟用 / 停用使用者"""
        result = self.collection.update_one(
            {"id": user_id},
            {"$set": {"disabled": disabled}},
        )
        if result.modified_count > 0:
            logger.info("[UserManager] 設定使用者 %s disabled=%s", user_id, disabled)
            return True
        return False

    def delete_user(self, user_id: str) -> bool:
        """刪除使用者"""
        result = self.collection.delete_one({"id": user_id})
        if result.deleted_count > 0:
            logger.info("[UserManager] 刪除使用者: %s", user_id)
            return True
        return False
