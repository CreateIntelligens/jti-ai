# User Scope Refactor (app → scope) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把貫穿 DB / JWT / 授權 / 前端的誤導欄位 `user.app`（目前同時存 `hciot`、`jti`、`general`、`key_name:<name>`）正名為 `user.scope`，並在 model 上提供 `scope_kind` / `scope_value` 推導屬性（不入庫），消除「欄位名與內容不符」的技術債。

**Architecture:** 單一字串欄位 `scope` 仍承載 app-scope（`hciot`/`jti`/`general`）或 key-scope（`key_name:<encoded>`）；`store_name` 維持為平行的第三種 scope。`scope_kind`（`store`/`key`/`app`）與 `scope_value` 由 `store_name` + `scope` **推導**而來，不新增入庫欄位（避免三欄同步債）。`verify_auth` 早已以 DB 為單一事實來源重抓使用者資料，故 JWT payload 內部欄位改名風險低；但 auth dict 對外仍以 **`scope` 取代 `app`** key，前端 `UserProfile`/`LoginResponse` 同步改名。舊 JWT 不需強制失效（DB 重抓），但 token payload 欄位會由 `app` 改為 `scope`，舊 token 的 `app` claim 僅在 user_manager 不可用時 fallback —— 為相容，decode 端同時讀 `scope` 與舊 `app`。

**Tech Stack:** FastAPI, Pydantic, PyJWT, MongoDB (pymongo), React, TypeScript, pytest, vitest.

**Migration 策略:** `scripts/migrate_user_scope.py` 手動執行，把既有 `users` 文件的 `app` 欄位 rename 成 `scope`（值不變）。不在 app 啟動時自動跑。與既有 `scripts/migrate_stores_app.py` 同寫法（`sys.path.insert` + 唯讀/冪等）。

**回滾:** migration 冪等（`app` 不存在則跳過）；欄位改名後若需回滾，反向 rename 即可。JWT decode 端相容舊 `app` claim，故部署順序無硬性要求。

---

## File Structure

| 檔案 | 職責 | 動作 |
|------|------|------|
| `app/users.py` | `User` model + `UserManager`：`app`→`scope`、加 `scope_kind`/`scope_value` 推導屬性、`create_user`/`list_users` 參數改名 | Modify |
| `app/security/tokens.py` | `create_session_token` 簽 `scope` claim（取代 `app`） | Modify |
| `app/auth.py` | `_resolve_session_auth`：讀 `user.scope`，auth dict 用 `scope` key（相容讀舊 `app` claim） | Modify |
| `app/routers/auth_routes.py` | login response 與 `/me` 回 `scope`（取代 `app`） | Modify |
| `app/routers/general/users.py` | create-user request / response schema：`app`→`scope` | Modify |
| `app/routers/general/chat.py` | 授權讀 `auth.get("scope")` | Modify |
| `app/routers/general/stores.py` | 授權讀 `auth.get("scope")` | Modify |
| `scripts/create_user.py` | CLI `--app` → `--scope` | Modify |
| `scripts/migrate_user_scope.py` | 既有 `users.app` → `users.scope` 改名 migration | Create |
| `frontend/src/services/api/auth.ts` | `UserProfile`/`LoginResponse`/相關型別 `app`→`scope` | Modify |
| `frontend/src/utils/authRouting.ts` | redirect / scope 判斷讀 `scope` | Modify |
| `frontend/src/components/UsersPanel.tsx` | 送出 `scope`（取代 `app`）、badge 讀 `scope` | Modify |
| 測試 | `tests/test_users.py`、`tests/general/test_users_api.py`、`tests/general/test_home_api_compat.py`、`frontend` auth routing 測試 | Modify |

**命名契約（後續任務一律遵守）:**
- Python：`User.scope: str | None`、`User.scope_kind -> str`（`"store"|"key"|"app"`）、`User.scope_value -> str | None`、`UserManager.create_user(..., scope=..., store_name=...)`、auth dict key `"scope"`。
- TypeScript：`UserProfile.scope: string | null`、`LoginResponse.scope: string | null`。
- 推導規則：`store_name` 非空 → kind `store`、value = `store_name`；否則 `scope` 以 `key_name:` 開頭 → kind `key`、value = decode 後的 key 名稱；否則 kind `app`、value = `scope`；`scope` 與 `store_name` 皆空 → kind `app`、value `None`。

---

### Task 1: User model 改名 + 推導屬性

**Files:**
- Modify: `app/users.py`
- Test: `tests/test_users.py`

- [ ] **Step 1: Write the failing test**

在 `tests/test_users.py` 的 `TestValidateRoleScope` 之後新增一個 class：

```python
class TestUserScopeDerivation:
    def _user(self, scope=None, store_name=None):
        return User(
            id="u1",
            username="u",
            password_hash="x",
            role="user",
            scope=scope,
            store_name=store_name,
        )

    def test_store_name_takes_precedence(self):
        u = self._user(scope="hciot", store_name="store_x")
        assert u.scope_kind == "store"
        assert u.scope_value == "store_x"

    def test_key_name_scope(self):
        u = self._user(scope="key_name:%E5%92%8C%E6%B3%B0%E6%B1%BD%E8%BB%8A")
        assert u.scope_kind == "key"
        assert u.scope_value == "和泰汽車"

    def test_plain_app_scope(self):
        u = self._user(scope="hciot")
        assert u.scope_kind == "app"
        assert u.scope_value == "hciot"

    def test_empty_scope(self):
        u = self._user()
        assert u.scope_kind == "app"
        assert u.scope_value is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_users.py::TestUserScopeDerivation -v`
Expected: FAIL（`User` 無 `scope` / `scope_kind` / `scope_value`）。

- [ ] **Step 3: 改 `User` model 欄位與推導屬性**

在 `app/users.py` 的 `User` model：把 `app: str | None = None` 改為 `scope: str | None = None`（保留註解說明它存 app 或 `key_name:<name>`）。在 model 內加入：

```python
from urllib.parse import unquote

class User(BaseModel):
    # ... 既有欄位，app 改名為 scope ...
    scope: str | None = None  # app(hciot/jti/general) 或 key scope(key_name:<encoded>);僅 role=user 有意義
    store_name: str | None = None

    @property
    def scope_kind(self) -> str:
        if self.store_name:
            return "store"
        if self.scope and self.scope.startswith("key_name:"):
            return "key"
        return "app"

    @property
    def scope_value(self) -> str | None:
        if self.store_name:
            return self.store_name
        if self.scope and self.scope.startswith("key_name:"):
            raw = self.scope[len("key_name:"):]
            try:
                return unquote(raw).strip() or None
            except Exception:
                return raw.strip() or None
        return self.scope or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_users.py::TestUserScopeDerivation -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add app/users.py tests/test_users.py
git commit -m "refactor(users): rename app field to scope with derived kind/value"
```

---

### Task 2: UserManager 參數改名 + 驗證沿用

**Files:**
- Modify: `app/users.py`
- Test: `tests/test_users.py`

- [ ] **Step 1: Update existing tests to use scope**

在 `tests/test_users.py`：
- `TestValidateRoleScope` 內所有 `_validate_role_scope(..., app=...)` 呼叫的 `app=` 參數改為 `scope=`（驗證函式內部參數名同步改）。
- `test_create_user_store_only_user_inserts` 與其他 `create_user(..., app=...)` 呼叫改為 `scope=`，並把斷言 `doc["app"]` 改為 `doc["scope"]`、`user.app` 改為 `user.scope`。

```python
    def test_invalid_role_raises(self):
        with pytest.raises(ValueError):
            UserManager._validate_role_scope("root", scope="jti")

    @pytest.mark.parametrize("role", ["super_admin", "admin"])
    def test_admin_roles_allow_none_scope(self, role):
        UserManager._validate_role_scope(role, scope=None, store_name=None)

    def test_user_role_requires_scope_or_store(self):
        with pytest.raises(ValueError, match="scope.*store_name|store_name.*scope"):
            UserManager._validate_role_scope("user", scope=None, store_name=None)

    def test_user_role_rejects_empty_scope(self):
        with pytest.raises(ValueError, match="scope.*store_name|store_name.*scope"):
            UserManager._validate_role_scope("user", scope="", store_name="")

    def test_user_role_with_scope_ok(self):
        UserManager._validate_role_scope("user", scope="hciot", store_name=None)

    def test_user_role_rejects_legacy_key_index_scope(self):
        with pytest.raises(ValueError, match="key_name"):
            UserManager._validate_role_scope("user", scope="key:1", store_name=None)

    def test_user_role_with_store_only_ok(self):
        UserManager._validate_role_scope("user", scope=None, store_name="store_hotai")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_users.py -v`
Expected: FAIL（`_validate_role_scope` / `create_user` 仍是 `app=` 參數名；訊息仍含「app」）。

- [ ] **Step 3: 改 UserManager**

在 `app/users.py`：

```python
    @staticmethod
    def _validate_role_scope(
        role: str,
        scope: str | None,
        store_name: str | None = None,
    ) -> None:
        """驗證角色與可存取範圍;不合法則丟 ValueError。

        - role 必須在 ALLOWED_ROLES 內
        - role == "user" 必須有非空 scope 或 store_name
        """
        if role not in ALLOWED_ROLES:
            raise ValueError(f"不合法的角色: {role!r} (允許: {sorted(ALLOWED_ROLES)})")
        if role == "user" and not (scope or store_name):
            raise ValueError("role=user 必須指定 scope 或 store_name")
        normalized = (scope or "").strip().lower()
        if role == "user" and normalized.startswith("key:"):
            raise ValueError("role=user 的 key scope 必須使用 key_name:<name>")
```

`create_user` 簽名與內部：把 `app` 參數改為 `scope`，呼叫 `self._validate_role_scope(role, scope, store_name)`，建立 `User(..., scope=scope, store_name=store_name)`。`list_users` 的 `app` 篩選參數改為 `scope`，query `{"scope": scope}`。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_users.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add app/users.py tests/test_users.py
git commit -m "refactor(users): rename app param to scope in UserManager"
```

---

### Task 3: JWT token 簽 scope claim

**Files:**
- Modify: `app/security/tokens.py`
- Test: `tests/`（若有 `tests/security/test_tokens.py` 則改之；否則於 `tests/general/test_users_api.py` 間接覆蓋，本任務僅需既有測試綠）

- [ ] **Step 1: 改 create_session_token 簽名與 payload**

在 `app/security/tokens.py`：`create_session_token(user_id, role, app)` 的第三參數改名為 `scope`，docstring 的 `app` 改 `scope`，payload `"app": app` 改為 `"scope": scope`。

```python
def create_session_token(
    user_id: str,
    role: str,
    scope: str | None,
    # ... 其餘參數不變 ...
) -> str:
    # ...
    payload = {
        "sub": user_id,
        "role": role,
        "scope": scope,
        # iat / exp 不變
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)
```

- [ ] **Step 2: Run existing token/auth tests**

Run: `python -m pytest tests/ -k "token or auth" -v`
Expected: 可能 FAIL（caller 仍傳 positional，但參數名改變不影響 positional；若有測試斷言 claim `"app"` 則需 Task 4 一併）。記錄結果，續做 Task 4。

- [ ] **Step 3: Commit**

```bash
git add app/security/tokens.py
git commit -m "refactor(tokens): sign scope claim instead of app"
```

---

### Task 4: auth.py 解碼讀 scope（相容舊 app claim）

**Files:**
- Modify: `app/auth.py`
- Modify: `app/routers/auth_routes.py`
- Test: `tests/general/test_users_api.py`

- [ ] **Step 1: 改 _resolve_session_auth**

在 `app/auth.py` `_resolve_session_auth`：

```python
    claims = decode_session_token(token)
    if not claims:
        return None

    user_id = claims.get("sub")
    role = claims.get("role")
    scope = claims.get("scope", claims.get("app"))  # 相容舊 token 的 app claim
    store_name = None

    from app import deps

    if deps.user_manager is not None:
        user = deps.user_manager.get_user(user_id) if user_id else None
        if user is None:
            raise HTTPException(status_code=401, detail="Session user not found")
        if getattr(user, "disabled", False):
            raise HTTPException(status_code=401, detail="User is disabled")
        role = user.role
        scope = user.scope
        store_name = user.store_name

    return {
        "role": role,
        "scope": scope,
        "store_name": store_name,
        "user_id": user_id,
    }
```

同步更新 `verify_auth` docstring 範例 dict 的 `"app"` → `"scope"`。

- [ ] **Step 2: 改 auth_routes login / me**

在 `app/routers/auth_routes.py`：
- login：`token = create_session_token(user.id, user.role, user.scope)`；回傳 `{"token": token, "role": user.role, "scope": user.scope}`。
- `/me`（或回 profile 的 route）：`"scope": auth.get("scope")`（取代 `"app": auth.get("app")`）。

- [ ] **Step 3: 更新 test_users_api 的 auth override**

在 `tests/general/test_users_api.py`：所有 `_override_auth({"role": ..., "app": None, ...})` 的 `"app"` key 改為 `"scope"`。create-user 請求 body 與斷言中的 `app` 隨 Task 5 schema 改名一併處理（本步先改 auth override key）。

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/general/test_users_api.py tests/ -k "auth" -v`
Expected: PASS（schema 相關失敗留待 Task 5）。

- [ ] **Step 5: Commit**

```bash
git add app/auth.py app/routers/auth_routes.py tests/general/test_users_api.py
git commit -m "refactor(auth): resolve scope from user, keep legacy app claim fallback"
```

---

### Task 5: create-user API schema 改名

**Files:**
- Modify: `app/routers/general/users.py`
- Test: `tests/general/test_users_api.py`

- [ ] **Step 1: 改 request/response schema**

在 `app/routers/general/users.py`：
- response model（含 `app: str | None`）的欄位 `app` 改為 `scope`，組裝時 `scope=user.scope`。
- create request model 的 `app` 改為 `scope`。
- 呼叫 `create_user(..., scope=request.scope, store_name=request.store_name, ...)`。

- [ ] **Step 2: 更新 test_users_api 請求與斷言**

在 `tests/general/test_users_api.py`：
- `test_admin_creates_user_role_ok` 等：請求 body `"app": "hciot"` → `"scope": "hciot"`；斷言 `resp.json()["app"]` → `["scope"]`；`create_user.assert_called_once_with(... app=...)` → `scope=`。
- `test_admin_creates_store_only_user_ok`：`assert resp.json()["app"] is None` → `["scope"] is None`；`assert_called_once_with(..., app=None, ...)` → `scope=None`。
- `test_create_user_without_scope_bad_request`：side_effect 訊息 `"role=user 必須指定 scope 或 store_name"`；斷言改為 `assert "scope" in detail` 與 `assert "store_name" in detail`。

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/general/test_users_api.py -v`
Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add app/routers/general/users.py tests/general/test_users_api.py
git commit -m "refactor(users-api): rename app to scope in create-user schema"
```

---

### Task 6: chat / stores 授權讀 scope

**Files:**
- Modify: `app/routers/general/chat.py`
- Modify: `app/routers/general/stores.py`
- Test: `tests/general/test_home_api_compat.py`

- [ ] **Step 1: 改授權讀取點**

- `app/routers/general/chat.py`：`_resolve_request_store` 內兩處 `auth.get("app")` 改為 `auth.get("scope")`（變數名可保留 `auth_app` 或更名 `auth_scope`，但兩處一致）。
- `app/routers/general/stores.py`：`_list_user_scoped_stores` 內 `auth.get("app")`（line ~500, ~503）改為 `auth.get("scope")`；其餘 `store_config_matches_scope` / `_dynamic_store_matches_scope` 邏輯不變（它們吃的是 scope 字串，與來源 key 名無關）。

- [ ] **Step 2: 更新 test_home_api_compat 的 auth override**

在 `tests/general/test_home_api_compat.py`：所有 `app.dependency_overrides[verify_auth] = lambda: {"role": "user", ..., "app": ...}` 的 `"app"` key 改為 `"scope"`。涵蓋：`test_legacy_key_index_scope_is_rejected`、`test_user_key_name_scope_survives_key_order_changes`、`test_user_without_store_lists_only_own_app_stores`、`test_user_with_store_lists_only_assigned_store`、`test_resolve_request_store_scope_authorization`、`test_resolve_request_store_rejects_legacy_key_index_scope` 等所有設 `"app"` 的 override。

- [ ] **Step 3: Run full backend suite**

Run: `python -m pytest -q`
Expected: PASS（282 → 286 左右，含 Task 1 新測試）。

- [ ] **Step 4: Commit**

```bash
git add app/routers/general/chat.py app/routers/general/stores.py tests/general/test_home_api_compat.py
git commit -m "refactor(general): read scope from auth in chat/stores authorization"
```

---

### Task 7: CLI 與 migration 腳本

**Files:**
- Modify: `scripts/create_user.py`
- Create: `scripts/migrate_user_scope.py`

- [ ] **Step 1: 改 create_user.py CLI**

在 `scripts/create_user.py`：`--app` argument 改為 `--scope`（help 文字說明可填 `hciot`/`jti`/`general`/`key_name:<name>`），呼叫 `create_user(..., scope=args.scope, ...)`。docstring 範例 `--app hciot` 改為 `--scope hciot`。

- [ ] **Step 2: 建立 migration 腳本**

Create `scripts/migrate_user_scope.py`：

```python
#!/usr/bin/env python3
"""Migration: rename users.app -> users.scope (值不變,冪等)。

在 backend 環境內執行:
    python scripts/migrate_user_scope.py
唯讀預覽:
    python scripts/migrate_user_scope.py --dry-run
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.users import UserManager  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate_user_scope")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    collection = UserManager().collection
    cursor = collection.find({"app": {"$exists": True}})
    count = 0
    for doc in cursor:
        value = doc.get("app")
        logger.info("user %s: app=%r -> scope (dry_run=%s)", doc.get("username"), value, args.dry_run)
        if not args.dry_run:
            collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"scope": value}, "$unset": {"app": ""}},
            )
        count += 1
    logger.info("done. %d users %s.", count, "previewed" if args.dry_run else "migrated")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 冒煙驗證（dry-run）**

Run（容器內，若 Mongo 可達）: `python scripts/migrate_user_scope.py --dry-run`
Expected: 列出既有帶 `app` 欄位的 user，不改資料。若本機無 Mongo，記錄為待容器內執行。

- [ ] **Step 4: Commit**

```bash
git add scripts/create_user.py scripts/migrate_user_scope.py
git commit -m "chore(users): add scope migration script and rename CLI flag"
```

---

### Task 8: 前端型別與 routing 改名

**Files:**
- Modify: `frontend/src/services/api/auth.ts`
- Modify: `frontend/src/utils/authRouting.ts`
- Test: `frontend/tests/`（authRouting 相關測試，若存在）

- [ ] **Step 1: 改型別**

在 `frontend/src/services/api/auth.ts`：`UserProfile`、`LoginResponse`、以及其他帶 `app: string | null` 的相關 interface（line 7/14/25/70 等），欄位 `app` 改為 `scope`。對應的 fetch/parse 程式若以 `data.app` 取值，改為 `data.scope`。

- [ ] **Step 2: 改 authRouting**

在 `frontend/src/utils/authRouting.ts`：

```typescript
export function isGeneralUserScope(profile: Pick<UserProfile, 'scope' | 'store_name' | 'role'>): boolean {
  if (isAdminRole(profile.role)) return false;
  if (profile.store_name) return true;
  if (profile.scope === 'general') return true;
  return Boolean(profile.scope?.startsWith('key_name:'));
}

export function getProfileRedirectPath(profile: Pick<UserProfile, 'scope' | 'store_name' | 'role'>): string {
  if (isGeneralUserScope(profile)) return '/';
  if (profile.scope === 'hciot') return '/hciot';
  if (profile.scope === 'jti') return '/jti';
  return '/login';
}

export function getLoginRedirectPath(profile: Pick<LoginResponse, 'role' | 'scope'>): string {
  if (isAdminRole(profile.role)) return '/';
  if (profile.role === 'user' && profile.scope === 'hciot') return '/hciot';
  if (profile.role === 'user' && profile.scope === 'jti') return '/jti';
  return '/';
}
```

- [ ] **Step 3: 更新 authRouting 測試**

若 `frontend/tests/` 有 authRouting 測試，把測試資料的 `app:` 改為 `scope:`。Grep 確認：`grep -rn "app:" frontend/tests/`。

- [ ] **Step 4: Run frontend typecheck + tests**

Run（在 `frontend/`）: `pnpm exec tsc --noEmit && pnpm test`
Expected: tsc 乾淨；vitest 全綠（會抓出 UsersPanel 尚未改的 `profile.app` 引用 → Task 9）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api/auth.ts frontend/src/utils/authRouting.ts frontend/tests/
git commit -m "refactor(frontend): rename app to scope in profile types and routing"
```

---

### Task 9: UsersPanel 送出 / 顯示 scope

**Files:**
- Modify: `frontend/src/components/UsersPanel.tsx`
- Modify: `frontend/src/App.tsx`（若有讀 `profile.app`）

- [ ] **Step 1: 改 UsersPanel submit payload 與 badge**

在 `frontend/src/components/UsersPanel.tsx`：
- 建立 user 的 payload：把 `app: role === 'user' && trimmedScope ? trimmedScope : null` 的 key 從 `app` 改為 `scope`（即 request body 送 `scope`）。
- user 列表 badge：`{u.app && (... scopeLabel(u.app) ...)}` 改為讀 `u.scope`（`api.UserAccount` 型別的欄位隨 Task 8 已改名）。

- [ ] **Step 2: 全域掃殘留 profile.app / .app 引用**

Run（在 `frontend/`）: `grep -rn "\.app\b\|app:" frontend/src/ | grep -iv "import\|App\b\|app/"`
逐一把 profile / store-scope 相關的 `.app` 改為 `.scope`（store payload 的 `managed_app` 不在此列，維持不動）。特別檢查 `frontend/src/App.tsx`、`useCurrentUserProfile` 等讀 profile 的地方。

- [ ] **Step 3: Run frontend typecheck + tests + build**

Run（在 `frontend/`）: `pnpm exec tsc --noEmit && pnpm test && pnpm build`
Expected: 全綠、build 成功。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/UsersPanel.tsx frontend/src/App.tsx
git commit -m "refactor(frontend): submit and display scope in UsersPanel"
```

---

### Task 10: 文件與全套驗證

**Files:**
- Modify: `docs/superpowers/specs/2026-06-02-auth-rbac-design.md`（補一節記錄 `app`→`scope` 改名）
- Modify: `docs/plans/2026-06-02-app-store-hierarchy-and-scope.md`（如提及 `user.app` 之處更新為 `scope`）

- [ ] **Step 1: 更新 spec**

在 `2026-06-02-auth-rbac-design.md` 加一小節：`user.app` 已正名為 `user.scope`，承載 app-scope 或 `key_name:<name>`；`scope_kind`/`scope_value` 為 model 推導屬性;`store_name` 為平行 scope。記錄 migration 腳本 `scripts/migrate_user_scope.py` 須手動執行。

- [ ] **Step 2: 全套驗證**

Run: `python -m pytest -q`
Expected: 全綠。

Run（在 `frontend/`）: `pnpm exec tsc --noEmit && pnpm test && pnpm build`
Expected: 全綠、build 成功。

Run: `grep -rn '"app"\|\.app\b\|app=' app/ scripts/ | grep -iv "FastAPI\|app =\|app\.\|app/\|fastapi"`
Expected: 後端授權 / user 相關已無殘留 `app` scope 欄位（FastAPI app 物件本身的 `app.` 不算）。

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "docs(auth): document app->scope rename and migration"
```

---

## 不做 / 邊界

- 不新增 `scope_kind` / `scope_value` 入庫欄位（純推導屬性）。
- 不在 app 啟動時自動 migration（手動跑 `scripts/migrate_user_scope.py`）。
- 不改 `store.managed_app`（store 端的 app 標記與 user.scope 無關，維持不動）。
- 不改 `api_keys` 的 `store_name`（sk-xxx key 綁定路徑形狀不變）。
- 不強制使既有 JWT 失效；decode 端相容舊 `app` claim。

## 一句話總結

> 把誤導的 `user.app` 欄位正名為 `user.scope`,以 `scope` + `store_name` 推導出 `scope_kind`/`scope_value`(不入庫),同步改 JWT claim、auth dict key、create-user schema、前端 profile 型別與 routing,並提供手動 rename migration——消除「欄位名與內容不符」的債,且不製造三欄同步的新債。
```
