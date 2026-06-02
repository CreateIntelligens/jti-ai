"""UserManager / User 測試。

純邏輯 (角色 / app 驗證、User 模型) 不需 Mongo;
Mongo 相關方法以 MagicMock 取代 collection 測試 (與 tests/storage 慣例一致)。
"""

import importlib.util
from unittest.mock import MagicMock

import pytest

from app.users import ALLOWED_ROLES, User, UserManager

HAS_BCRYPT = importlib.util.find_spec("bcrypt") is not None
requires_bcrypt = pytest.mark.skipif(not HAS_BCRYPT, reason="bcrypt 未安裝")


# --- 純邏輯: 角色 / app 驗證 (不需 Mongo) ---

class TestValidateRoleScope:
    def test_allowed_roles_set(self):
        assert ALLOWED_ROLES == {"super_admin", "admin", "user"}

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError):
            UserManager._validate_role_scope("root", app="jti")

    @pytest.mark.parametrize("role", ["super_admin", "admin"])
    def test_admin_roles_allow_none_app(self, role):
        # 不丟例外
        UserManager._validate_role_scope(role, app=None, store_name=None)

    def test_user_role_requires_app_or_store(self):
        with pytest.raises(ValueError, match="app.*store_name|store_name.*app"):
            UserManager._validate_role_scope("user", app=None, store_name=None)

    def test_user_role_rejects_empty_scope(self):
        with pytest.raises(ValueError, match="app.*store_name|store_name.*app"):
            UserManager._validate_role_scope("user", app="", store_name="")

    def test_user_role_with_app_ok(self):
        UserManager._validate_role_scope("user", app="hciot", store_name=None)

    def test_user_role_rejects_legacy_key_index_scope(self):
        with pytest.raises(ValueError, match="key_name"):
            UserManager._validate_role_scope("user", app="key:1", store_name=None)

    def test_user_role_with_store_only_ok(self):
        UserManager._validate_role_scope("user", app=None, store_name="store_hotai")


# --- 純邏輯: User 模型 ---

class TestUserModel:
    def test_defaults(self):
        u = User(username="alice", password_hash="h", role="admin")
        assert u.id.startswith("user_")
        assert u.app is None
        assert u.store_name is None
        assert u.created_by is None
        assert u.disabled is False
        assert isinstance(u.created_at, str) and u.created_at

    def test_unique_ids(self):
        a = User(username="a", password_hash="h", role="admin")
        b = User(username="b", password_hash="h", role="admin")
        assert a.id != b.id


# --- Mongo 相關: 以 MagicMock 取代 collection ---

def _manager_with_mock_collection():
    """繞過 __init__ 的 MongoClient,注入 mock collection。"""
    mgr = UserManager.__new__(UserManager)
    mgr.collection = MagicMock()
    return mgr


class TestUserManagerMongo:
    def test_create_user_invalid_role_raises_before_db(self):
        mgr = _manager_with_mock_collection()
        with pytest.raises(ValueError):
            mgr.create_user("bob", "pw", role="root")
        mgr.collection.insert_one.assert_not_called()

    def test_create_user_user_role_without_scope_raises_before_db(self):
        mgr = _manager_with_mock_collection()
        with pytest.raises(ValueError):
            mgr.create_user("bob", "pw", role="user")
        mgr.collection.insert_one.assert_not_called()

    @requires_bcrypt
    def test_create_user_hashes_password_and_inserts(self):
        mgr = _manager_with_mock_collection()
        user = mgr.create_user("carol", "pw123", role="user", app="jti")
        assert user.username == "carol"
        assert user.role == "user"
        assert user.app == "jti"
        # 不存明文
        assert user.password_hash != "pw123"
        doc = mgr.collection.insert_one.call_args[0][0]
        assert doc["password_hash"] != "pw123"
        assert "_id" not in doc

    @requires_bcrypt
    def test_create_user_store_only_user_inserts(self):
        mgr = _manager_with_mock_collection()
        user = mgr.create_user(
            "hotai-user",
            "pw123",
            role="user",
            app=None,
            store_name="store_hotai",
        )
        assert user.app is None
        assert user.store_name == "store_hotai"
        doc = mgr.collection.insert_one.call_args[0][0]
        assert doc["app"] is None
        assert doc["store_name"] == "store_hotai"

    @requires_bcrypt
    def test_verify_credentials_success(self):
        mgr = _manager_with_mock_collection()
        from app.security.passwords import hash_password
        stored = User(
            username="dave", password_hash=hash_password("secret"), role="admin"
        ).model_dump()
        mgr.collection.find_one.return_value = dict(stored, _id="x")
        result = mgr.verify_credentials("dave", "secret")
        assert result is not None
        assert result.username == "dave"

    @requires_bcrypt
    def test_verify_credentials_wrong_password(self):
        mgr = _manager_with_mock_collection()
        from app.security.passwords import hash_password
        stored = User(
            username="dave", password_hash=hash_password("secret"), role="admin"
        ).model_dump()
        mgr.collection.find_one.return_value = dict(stored, _id="x")
        assert mgr.verify_credentials("dave", "wrong") is None

    def test_verify_credentials_unknown_user(self):
        mgr = _manager_with_mock_collection()
        mgr.collection.find_one.return_value = None
        assert mgr.verify_credentials("ghost", "pw") is None

    @requires_bcrypt
    def test_verify_credentials_disabled_user(self):
        mgr = _manager_with_mock_collection()
        from app.security.passwords import hash_password
        stored = User(
            username="dave",
            password_hash=hash_password("secret"),
            role="admin",
            disabled=True,
        ).model_dump()
        mgr.collection.find_one.return_value = dict(stored, _id="x")
        assert mgr.verify_credentials("dave", "secret") is None

    def test_get_user_pops_id(self):
        mgr = _manager_with_mock_collection()
        doc = User(username="e", password_hash="h", role="admin").model_dump()
        mgr.collection.find_one.return_value = dict(doc, _id="x")
        u = mgr.get_user(doc["id"])
        assert u is not None and u.username == "e"

    def test_get_user_missing(self):
        mgr = _manager_with_mock_collection()
        mgr.collection.find_one.return_value = None
        assert mgr.get_user("nope") is None

    def test_get_by_username(self):
        mgr = _manager_with_mock_collection()
        doc = User(username="f", password_hash="h", role="admin").model_dump()
        mgr.collection.find_one.return_value = dict(doc, _id="x")
        u = mgr.get_by_username("f")
        assert u is not None and u.username == "f"
        assert mgr.collection.find_one.call_args[0][0] == {"username": "f"}

    def test_list_users_sorted_desc(self):
        mgr = _manager_with_mock_collection()
        docs = [
            dict(User(username="g", password_hash="h", role="admin").model_dump(), _id="1"),
            dict(User(username="h", password_hash="h", role="admin").model_dump(), _id="2"),
        ]
        cursor = MagicMock()
        cursor.sort.return_value = docs
        mgr.collection.find.return_value = cursor
        result = mgr.list_users()
        assert len(result) == 2
        cursor.sort.assert_called_once_with("created_at", -1)
        assert mgr.collection.find.call_args[0][0] == {}

    def test_list_users_filters_role_and_app(self):
        mgr = _manager_with_mock_collection()
        cursor = MagicMock()
        cursor.sort.return_value = []
        mgr.collection.find.return_value = cursor
        mgr.list_users(role="user", app="jti")
        assert mgr.collection.find.call_args[0][0] == {"role": "user", "app": "jti"}

    def test_set_disabled(self):
        mgr = _manager_with_mock_collection()
        mgr.collection.update_one.return_value = MagicMock(modified_count=1)
        assert mgr.set_disabled("user_1", True) is True
        update = mgr.collection.update_one.call_args[0]
        assert update[0] == {"id": "user_1"}
        assert update[1] == {"$set": {"disabled": True}}

    def test_set_disabled_no_match(self):
        mgr = _manager_with_mock_collection()
        mgr.collection.update_one.return_value = MagicMock(modified_count=0)
        assert mgr.set_disabled("nope", True) is False

    def test_delete_user(self):
        mgr = _manager_with_mock_collection()
        mgr.collection.delete_one.return_value = MagicMock(deleted_count=1)
        assert mgr.delete_user("user_1") is True
        assert mgr.collection.delete_one.call_args[0][0] == {"id": "user_1"}

    def test_delete_user_no_match(self):
        mgr = _manager_with_mock_collection()
        mgr.collection.delete_one.return_value = MagicMock(deleted_count=0)
        assert mgr.delete_user("nope") is False
