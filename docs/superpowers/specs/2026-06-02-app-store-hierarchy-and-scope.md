# App↔Store 層級、知識庫下拉與範圍授權 — 實作追蹤

- **日期**：2026-06-02
- **狀態**：Draft（已依選項 B 補實作；待 spark 驗收後再改 Done）
- **分支 / 工作區**：`feat/rag`（worktree: `.worktrees/jtai-rag`）
- **預期執行者**：待驗收

---

## 0. 這份文件是什麼

Auth/RBAC + app-key-map 收斂後，原本待決策的「app 底下有哪些 store」已採用 **選項 B：dynamic store 顯式帶 `managed_app` 欄位** 落地。

本文件保留 Draft 狀態，是因為 plan/spec 需等 spark 明確確認後才可改 Done；但 code 已補上資料模型、store list 篩選、user 建立下拉、chat scope 授權與測試。

相關既有文件：
- `2026-06-02-auth-rbac-design.md`（三層 role + 登入）
- `2026-06-02-app-key-map.md`（app→key 映射）

## 1. 目前已落地的資料模型

### 1.1 三層綁定鏈
```
GEMINI_API_KEYS (多把 key, 名稱:key)
   ▲ key_index / APP_KEY_MAP 名稱比對
store (managed_app + key_index)
   ▲ user.app / user.store_name
user (role + app + store_name)
```

### 1.2 managed store
- `app/routers/general/stores.py` 的 `MANAGED_STORES` 仍是固定 store。
- `__jti__` / `__jti__en` 屬於 `jti`。
- `__hciot__` / `__hciot__en` 屬於 `hciot`。
- managed store 的 key index 透過 `APP_KEY_MAP` 解析，不在 `stores.py` 寫死 key 顯示名。

### 1.3 dynamic store
- dynamic store payload 現在包含 `managed_app`，缺值時以 `general` 呈現。
- 建立 dynamic store 時，後端用 `key_index` 反查 `APP_KEY_MAP`，可對應到 `jti` / `hciot` 就寫入該 app；對不到則寫入 `general`。
- 既有資料補欄位由 `scripts/migrate_stores_app.py` 處理；此 migration 需手動執行，不在 app 啟動時自動改資料。

## 2. Store List 與授權規則

### 2.1 `GET /api/stores`
- admin / super_admin：維持可列所有 stores；可用 `?app=jti|hciot|general` 篩選。
- user 且有 `store_name`：只列該綁定 store；若 request 的 `?app=` 或 auth app 與該 store 的 `managed_app` 不一致，回 403。
- user 且無 `store_name`：必須有 `app`；只列該 app 底下 stores；若 `?app=` 跨 app，回 403。

### 2.2 Chat Scope
- user 有 `store_name`：chat 強制使用該 store，忽略 request body 的 store。
- user 有 `store_name` 且同時有 `app`：該 store 的 `managed_app` 必須與 auth app 一致，不一致回 403。
- user 無 `store_name` 但有 `app`：可 chat 該 app 底下任一 store；跨 app 回 403。
- user 無 `store_name` 且無 `app`：回 403。

## 3. 前端狀態

### 3.1 建 user 的知識庫下拉
- `UsersPanel` 的「綁定知識庫名稱」已從文字 input 改成 select。
- 選項由目前選定 app 過濾 stores。
- 空值代表「不選（此 App 下所有知識庫）」；送出時 `store_name=null`。

### 3.2 建 store 權限
- 維持原決議：`create_store` 仍需 admin / super_admin。
- 不新增「只有 super_admin 可建 key/store」這類分級。

## 4. 驗收標準

- [ ] `python -m pytest -q` 全綠。
- [ ] `frontend` 內 `pnpm exec tsc --noEmit` 全綠。
- [ ] `frontend` 內 `pnpm build` 成功。
- [ ] `GET /api/stores?app=hciot` 只回 HCIoT managed stores 與 `managed_app=hciot` 的 dynamic stores。
- [ ] user 無 `store_name`、有 `app=hciot` 時，只能列 / chat HCIoT stores。
- [ ] user 有 `store_name` 時，只能列 / chat 該 store。
- [ ] user scope 跨 app 時回 403。
- [ ] `scripts/migrate_stores_app.py` 可手動補既有 dynamic stores 的 `managed_app`。

## 5. 不做 / 邊界

- 不在 app 啟動時自動 migration 既有 dynamic stores。
- 不改建 key/store 權限分級。
- 不把 plan/spec 狀態改 Done，直到 spark 明確確認驗收完成。

## 6. 一句話總結

> 已把原本缺地基的 app↔store 樹狀關係落到 `managed_app` 欄位：dynamic store 建立時寫入 app，store list 與 chat 都按 user 的 app/store scope 授權，前端建 user 改用依 app 過濾的 store 下拉。
