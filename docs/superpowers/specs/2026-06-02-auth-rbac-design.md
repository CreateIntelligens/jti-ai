# JTAI 認證與三層角色（RBAC）設計文件

- **日期**：2026-06-02（v1 初版）
- **狀態**：Draft（技術評估，尚未落地）
- **分支**：`feat/rag`（worktree: `.worktrees/jtai-rag`）
- **作者協作對象**：spark.cs.liao
- **預期執行者**：Claude（可接受其他 AI 監督檢視）

---

## 1. 背景與動機

現階段需求：

- 客戶先拿到**一組帳密**登入，使用某一個 app（例如 hciot）。
- 我們自己要有 **admin / super_admin 全權限**，能建立並管理帳號。
- 之後可能對外開放，因此**現在就要把架構做完整，不留技術債**。

現有 `app/auth.py` 已有雛形，但僅兩層且有安全隱患（見 §7）：

- **admin**：同 origin（前端）請求自動視為 admin，或持 `ADMIN_API_KEY`。
- **user**：持 MongoDB 的 `sk-xxx` api_key，綁定單一 `store_name` + `prompt_index`。

本設計把它升級為**三層 role + 帳密登入 + general 後台管理 UI**。

## 2. 核心設計決策

經討論收斂出三個關鍵決策：

1. **role = 權限等級**（super_admin / admin / user），與 app 無關。
2. **一帳號只對一個 app**。因此 **app 不是權限維度，只是帳號的一個分類標籤兼登入導向依據**，不參與權限判斷（YAGNI：不做 `allowed_apps` 陣列、不做 `require_app()`）。
3. **app 內容對 user 與 admin 同樣可編輯**。hciot 沒有「使用者體驗 / 管理體驗」之分，進去就是可編輯工作區。
   → 因此 **user 與 admin 的分水嶺，只剩「能不能進 general 後台管理帳號」**。

## 3. 權限模型

| | 用 app（編輯內容） | 進 general 後台 | 管理帳號 |
|---|:---:|:---:|:---:|
| **user** | ✅ 僅自己所屬的 app | ❌ | ❌ |
| **admin** | ✅ 任何 app | ✅ | ✅ 只能管 user |
| **super_admin** | ✅ 任何 app | ✅ | ✅ 管所有人（含 admin）、系統設定 |

- **super_admin**：我們自己，通吃。
- **admin**：之後對外時給客戶的管理者；能建/管 user，但不能建別的 admin、不能改系統設定。
- **user**：客戶端使用者；能完整使用+編輯所屬 app，但進不了後台。

## 4. 登入與導向流程

```
/login  (首頁登入口)
   │ 帳密 → 驗證 → { role, app }
   │
   ├─ user ──────────► 導向 app[該帳號]            例:/hciot、/jti
   │                    ├ 可編輯該 app 內容
   │                    ├ 右上角「登出」鈕 → /login
   │                    └ 直接打 /general → 403,踢回自己的 app
   │
   └─ admin / super_admin ─► /general 後台
                              ├ 帳號管理(建/改 user;super_admin 還能管 admin)
                              └ 選單:前往 hciot / jti
                                       ├ 進去一樣可編輯
                                       └「返回後台」回 /general
```

- **導向由 `role + app` 決定**：user 看 `app` 欄位導去對應頁；admin/super_admin 一律進 `/general`。
- **權限判斷只看 `role`**：`app` 欄位完全不進權限邏輯。
- **跨 app 資料隔離**由既有的 `store_name` 綁定自然達成（key 綁哪個 store 就只看得到那個 store），不需要額外 app 檢查。

## 5. 資料模型（MongoDB）

新增 `users` collection 作為身分主體；role 存在 user 上。

```
users
  _id
  username            # 客戶登入用,唯一
  password_hash       # argon2 或 bcrypt,絕不存明碼
  role                # "super_admin" | "admin" | "user"
  app                 # "hciot" | "jti" | "general" — 單數字串(分類 + 登入導向)
  store_name          # 沿用現有 store 綁定;app 內容隔離靠這個
  created_by          # 哪個帳號建立的(稽核)
  created_at
  disabled            # 軟刪除 / 停用
```

**不留技術債的關鍵：**

- **`app` 是單一字串，不是陣列**——對應「一帳號只對一個 app」。它只用於登入導向與後台分組，**不參與權限**。
- **密碼從一開始就 argon2/bcrypt 雜湊**，不先存明碼再補。
- **role 與 app 兩個欄位分離但語意正交**：role 管「能做多大的事」，app 管「屬於哪個應用」。

### 與既有 `api_keys` collection 的關係

- `api_keys`（`sk-xxx` → store_name）**保留**，作為 programmatic / service token 用途。
- 其 `role` 不再寫死；視為服務憑證或繼承綁定帳號的脈絡。
- 人類登入改走帳密 → session JWT（見 §6）。

## 6. auth.py 升級

`verify_auth` 升級為同時支援多種憑證來源，並統一回傳 `{ "role", "app", "store_name", "user_id" }`：

1. **session JWT**（帳密登入的人類使用者）→ 解出 `user_id`，查 `users` 帶出 `role` / `app` / `store_name`。
2. **`ADMIN_API_KEY`** → `super_admin`（我們自己的後門，保留）。
3. **`sk-xxx` api_key** → 查 `api_keys`，帶出綁定脈絡（service 用途）。
4. **同 origin 前端 → 不再自動視為 admin**（拔掉現有安全洞，見 §7）。

權限 gate 只需要 `require_role`，**不需要 `require_app`**：

```python
def require_role(*allowed: str):
    def checker(auth = Depends(verify_auth)):
        if auth["role"] not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return auth
    return checker
```

三條使用方式：

```python
# app 內容編輯 API:登入即可(三種 role 都行)
dependencies=[Depends(require_role("user", "admin", "super_admin"))]

# general 後台 API:擋掉 user
dependencies=[Depends(require_role("admin", "super_admin"))]

# 管理 admin 帳號 / 系統設定:只有 super_admin
dependencies=[Depends(require_role("super_admin"))]
```

## 7. ⚠️ 必須處理的既有安全洞

現有 `auth.py` 的 `_is_same_origin()`：**任何同 origin（瀏覽器連到前端）的請求自動被視為 admin**。

- 現在內部使用無妨。
- **一旦對外開放，等於任何人開瀏覽器就是 admin——嚴重權限漏洞。**
- 升級時這條必須拔掉，改成「同 origin 也要登入、也要驗 session JWT」。

這正是「不留技術債」要一併解決的項目，不可遺漏。

## 8. general 後台 UI（UsersPanel）

對齊現有 general 的 `ApiKeysPanel` / store 管理面板，新增 **`UsersPanel`**：

```
┌─ 帳號管理 ─────────────────────────────────┐
│  [+ 新增帳號]                    篩選:[all ▾] │
├───────────────────────────────────────────┤
│  username   role         app     狀態   操作  │
│  cust_a     user         hciot   啟用   ✎ ⏻  │
│  cust_b     user         jti     啟用   ✎ ⏻  │
│  manager1   admin        —       啟用   ✎ ⏻  │
│  spark      super_admin  —       啟用   (鎖)  │
└───────────────────────────────────────────┘

新增帳號表單:
  username  [__________]
  初始密碼  [__________]
  role      ( ) user  ( ) admin  ( ) super_admin
  app       [hciot ▾]   ← 只有 role=user 時需要;admin/super_admin 可留空
```

- **role 顯示分級**：admin 只看得到/能建 `user`；`admin`、`super_admin` 選項與「改 role」只有 super_admin 可見。
- **app 欄位**：只在 `role=user` 時要求填（決定他登入後導向哪）；admin/super_admin 不綁 app。
- super_admin 自己的帳號不可被 admin 編輯/停用（鎖）。

## 9. 實作範圍清單

### Phase 1：後端地基 — ✅ 已完成（2026-06-02）

- [x] `users` collection schema + index（username 唯一）→ `app/users.py`
- [x] 密碼雜湊工具（bcrypt）→ `app/security/passwords.py`
- [x] `POST /login`（帳密 → session JWT）、`POST /logout` → `app/routers/auth_routes.py`
- [x] `auth.py`：`verify_auth` 支援 session JWT；新增 `require_role` → `app/auth.py`
- [x] general 後台帳號管理 API（建/改/停用，依 role 分級）→ `app/routers/general/users.py`
- [x] JWT 工具 → `app/security/tokens.py`；`deps.user_manager` 已接上
- 後端全測試：`258 passed, 9 skipped`（skip 為 bcrypt round-trip，待 `pip install -r requirements.txt`）

### Phase 2：前端 + 安全 cut-over — ⏳ 待做（見 §11 交接）

- [ ] 前端 `/login` 頁 + 登入後導向邏輯（role+app）
- [ ] 前端 general `UsersPanel`
- [ ] app 頁面角落「登出」鈕
- [ ] admin 在 general 的「前往 hciot/jti」選單 + 「返回後台」
- [ ] user 直連 `/general` → 403 並導回自身 app
- [ ] **§7 拔掉 `_is_same_origin` 自動 admin —— 必須與 login 頁同一 PR cut-over**

## 10. 一句話總結

> **role（super_admin/admin/user）存在 user 主體上、決定權限大小；app 是單一標籤、只決定登入導向與後台分組、不進權限邏輯。user 與 admin 唯一差別是「能否進 general 後台管帳號」。auth.py 由兩層升三層、加帳密登入,並拔掉「同 origin 自動 admin」這個對外會爆的設定。**

---

## 11. Phase 2 交接（給接手的開發者 / AI）

> 這一節是 Phase 2 的可執行工單。Phase 1 後端已完成且測試通過（§9）。接手者只需做前端 + 安全 cut-over。**動工前務必讀完 §11.1 的順序警告。**
> 工作區：worktree `/home/human/jtai/.worktrees/jtai-rag`（分支 `feat/rag`）。沿用 TDD（前端 vitest，後端 pytest）。前端用 `pnpm`、CSS 用相對單位（rem/%/vh，勿新增 px）。

### 11.1 ⚠️ 絕對的順序警告（最重要）

`app/auth.py` 的 `_is_same_origin()` → 回 `admin`，是**前端目前唯一**取得 admin 的方式。
前端 `frontend/src/services/api/base.ts` 的 `fetchAsAdmin()` 不送任何 token，admin 呼叫全靠同 origin 自動放行。

- **不可以**在還沒做好 `/login` 頁 + 帶 token 的請求流程前，就拔掉 `_is_same_origin` 的 admin 分支。
- 一旦先拔，整個 live 前端的 admin API 會全變 401，且當下沒有登入頁可恢復 → 直接弄爆運行中的 app。
- **正確順序**：先做 §11.3 ~ §11.5（login 頁、token 帶入、導向、登出），整條登入流程在前端跑通後，**最後一步**才在同一個 PR 內拔掉 `_is_same_origin` 自動 admin（§11.6）。

### 11.2 Phase 1 已就緒的後端介面（直接接，勿改）

**登入 / 登出**（`app/routers/auth_routes.py`，prefix `/api/auth`）：
- `POST /api/auth/login`　body `{ "username": str, "password": str }`
  - 成功 `200` → `{ "token": str, "role": "super_admin"|"admin"|"user", "app": str|null }`，並 set httpOnly cookie `session=<token>`。
  - 失敗 `401` → `{ "detail": "Invalid credentials" }`（通用訊息，不分帳號/密碼）。
- `POST /api/auth/logout` → 清 `session` cookie，回 `{ "ok": true }`。

**帳號管理**（`app/routers/general/users.py`，prefix `/api`，全部需 `require_role("admin","super_admin")`）：
- `GET /api/users?role=&app=` → `list[UserOut]`
- `POST /api/users` body `{ username, password, role, app?, store_name? }` → `201` `UserOut`
  - caller=admin 只能建 `role="user"`，否則 `403`；caller=super_admin 不限。
  - `ValueError`（如 role=user 沒給 app）→ `400`；username 重複 → `409`。
- `PATCH /api/users/{user_id}/disabled` body `{ disabled: bool }` → `UserOut`
  - admin 只能對 `role="user"` 的目標；super_admin 不限但不可停用自己（`400`）。
- `DELETE /api/users/{user_id}` → `{ "message": "使用者已刪除" }`；不存在 `404`；授權規則同 PATCH。

`UserOut` 欄位：`id, username, role, app, store_name, created_by, created_at, disabled`（**無** password_hash）。

**驗證機制**（`app/auth.py`）：
- 帶 `Authorization: Bearer <token>` 或 `API-Token: <token>` 的 session JWT → `verify_auth` 解出 `{role, app, store_name, user_id}`；user 被停用或不存在 → `401`。
- `require_role(*allowed)` 是 FastAPI dependency；`require_admin` 接受 `{admin, super_admin}`。
- 環境變數：需設 `SESSION_JWT_SECRET`（未設會 fallback 到 `ADMIN_API_KEY`）。

### 11.3 前端 token 流程（`frontend/src/services/api/base.ts`）

目前 `fetchAsAdmin` 不送 token、`fetchWithApiKey` 只在有 user key 時送 `API-Token`。Phase 2 要：
1. 登入成功後保存 token（cookie 已由後端 set；另建議存一份於 memory / context 供 Bearer header 用）。
2. 改為所有請求都帶 `Authorization: Bearer <session token>`（cookie 亦可，但顯式 Bearer 較不依賴 same-site）。
3. 收到 `401` → 導向 `/login`。

### 11.4 登入頁與導向（`frontend/src/App.tsx` + 新增 `/login` route）

現況：`App.tsx` 用 `react-router-dom`，已有 `/jti`、`/hciot`、`/`(home) routes + `canShow()` gate。新增：
- `/login` 頁（帳密表單，呼叫 `POST /api/auth/login`）。
- 登入後依回傳導向：
  - `role="user"` → 導去該帳號的 `app`（`/hciot` 或 `/jti`）。
  - `role="admin" | "super_admin"` → 導去 general 後台（`/`）。
- 未登入存取任何受保護 route → redirect `/login`。
- `role="user"` 直接打 general 後台路徑 → 擋下並導回自身 app。

### 11.5 後台 UI 與登出

- **UsersPanel**（general 後台，參考既有 `frontend/src/components/ApiKeysPanel.tsx` 風格）：列表 + 新增/停用/刪除，依 §8 的 role 分級顯示；接 §11.2 的 `/api/users` 系列。
- **登出鈕**：hciot / jti 頁面角落，呼叫 `POST /api/auth/logout` 後導回 `/login`。
- **admin 導覽**：general 後台加「前往 hciot / jti」入口 + 各 app 內「返回後台」。

### 11.6 最後一步：拔掉 same-origin 自動 admin（§7）

確認 §11.3~11.5 在前端跑通、所有 admin 呼叫都帶 token 後，於**同一個 PR**：
- 移除 `app/auth.py` `verify_auth` 中「無 token 且 same-origin → admin」的分支（改成無 token 一律 `401`）。
- 同步更新 `tests/test_auth.py` 那 3 個 same-origin 測試（它們現在斷言 same-origin == admin，cut-over 後要改成預期 `401`）。
- 移除/簡化 `base.ts` 的 same-origin fallback 邏輯。
- 回歸：`python -m pytest -q` 後端全綠 + 前端 `pnpm test` 全綠 + 手動驗證登入→各角色導向→登出。

### 11.7 驗收標準（我方驗收會檢查）

- [ ] 後端 `python -m pytest -q` 全綠（含被改寫的 same-origin 測試）。
- [ ] 前端 `pnpm test` 與 `pnpm exec tsc --noEmit` 全綠。
- [ ] 三種角色登入導向正確；user 進不了後台；admin 能管 user、super_admin 能管 admin 且不能停自己。
- [ ] 登出後 protected route 會踢回 `/login`。
- [ ] `_is_same_origin` 自動 admin 已移除，且無殘留「不帶 token 也能 admin」的路徑。
- [ ] CSS 用相對單位、無新增 px；無 `console.log` 殘留。
