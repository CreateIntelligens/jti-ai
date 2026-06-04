# 知識庫 Scope-based 授權設計文件

- **日期**：2026-06-04（v1 初版）
- **狀態**：Draft（尚未落地）
- **分支**：`feat/rag`（worktree: `.worktrees/jtai-rag`）
- **預期執行者**：Claude
- **關聯**：[2026-06-02-auth-rbac-design.md](./2026-06-02-auth-rbac-design.md)（三層 role 基礎）、[2026-06-02-app-store-hierarchy-and-scope.md](./2026-06-02-app-store-hierarchy-and-scope.md)

---

## 1. 背景與動機

目前所有知識庫管理端點（HCIoT / JTI 的 knowledge files、images、topics）一律用 `verify_admin` 守門，只接受 `admin` / `super_admin`。

實際需求：**一般使用者帳號（`role=user`，綁定某個 app 的 scope）應該要能管理「自己 app」的知識庫**，但不能碰別的 app。

現況問題（實際遇到）：帳號 `hciot`（`role=user`, `scope=hciot`）登入後，知識庫 workspace 三個請求全 403：

- `GET /api/hciot-admin/knowledge/files/`
- `GET /api/hciot-admin/images/`
- `GET /api/admin/rag/status?source_type=hciot`

根因經 `/api/auth/me` 確認：後端正確認得此帳號，但 `role=user` 未通過 `require_admin`，屬正確拒絕。需求是放寬規則，不是改帳號權限。

## 2. 核心設計決策

| 決策 | 選擇 | 理由 |
|---|---|---|
| app 歸屬怎麼判定 | 每個 router 建立時**明確帶入自己的 app 名** | 不靠 URL 字串推斷，明確、不脆弱，與既有 `qa_kb_router` 工廠化模式一致 |
| 授權規則 | super_admin 全通 / admin 跨所有 app / user 限同 scope | 符合「user 管自己 app」需求 |
| admin 跨 app | **admin 可跨所有 app**（不受 scope 限） | 依使用者決定；只有 scope 限制套在 user 身上 |
| 套用範圍 | HCIoT 與 JTI **都套**，行為一致 | 兩者共用 `qa_kb_router` 工廠，一次到位避免兩 app 規則分歧 |
| 知識庫範圍 | knowledge files + images + topics（整個 workspace） | 三者合起來才是完整知識庫管理；files 與 images 本就一起載入 |
| 對話歷史 | **維持 admin-only** | conversations 含用戶隱私，不放寬給一般 user |

## 3. 授權規則

新增 dependency factory `require_kb_access(app: str)`。判斷邏輯（純函式 `can_access_kb` 承載，便於測試）：

```
can_access_kb(auth, app) -> bool:
    role = auth["role"]
    if role == "super_admin":  return True        # scope=None，全通
    if role == "admin":        return True        # 跨所有 app
    if role == "user":         return auth.get("scope") == app
    return False
```

dependency 形態：

```python
def require_kb_access(app: str):
    def _dep(request: Request) -> dict:
        auth = verify_auth(request)               # 沿用既有：解 cookie/token → role/scope
        if not can_access_kb(auth, app):
            raise HTTPException(status_code=403, detail="Insufficient permission for this knowledge base")
        return auth
    return _dep
```

`verify_auth` 維持不變（已支援 cookie / bearer / api-token，且 JWT 以 DB role 為單一事實來源）。

## 4. 改動清單

| 檔案 | 改動 | 邊界 |
|---|---|---|
| `app/auth.py` | 新增純函式 `can_access_kb(auth, app)` 與 factory `require_kb_access(app)`。`verify_admin` / `require_admin` **保留不動**（對話歷史等仍用） | 只加，不刪既有 |
| `app/routers/_shared/qa_kb_router.py` | `QaKbRouterConfig` 新增 `app: str` 欄位；`build_qa_kb_router` 改用 `require_kb_access(config.app)` 取代 `Depends(config.auth_dep)`。`auth_dep` 欄位視情況保留以相容或移除 | 工廠層，一改同時影響走工廠的 HCIoT/JTI knowledge+extract 端點 |
| `app/routers/hciot/knowledge.py`、`qa_extract.py` | 建 config 時帶 `app="hciot"`（守門改由工廠用 `require_kb_access`） | — |
| `app/routers/hciot/images.py` | `admin_router` 的 `dependencies` 從 `Depends(verify_admin)` 改 `Depends(require_kb_access("hciot"))` | 獨立 router，逐個換 |
| `app/routers/hciot/topics_admin.py` | 同 images，`require_kb_access("hciot")` | — |
| `app/routers/hciot/chat.py` | **不動**——history router 維持 `verify_admin` | 對話歷史 admin-only |
| `app/routers/jti/*.py`（對應 knowledge/images/topics 端點） | 對應改為 `require_kb_access("jti")` | 與 HCIoT 一致 |

`/api/admin/rag/status`（reindex 狀態，`general.ts` 打的那支）若也要放寬給 scope user，需確認該端點守門位置；本設計預設一併納入「整個 workspace」放寬範圍，實作時確認其 router 並套同規則。

## 5. 測試

`can_access_kb` 純函式單元測試（`tests/` 既有慣例，無 class、`from app.auth import can_access_kb`）：

| 案例 | auth | app | 預期 |
|---|---|---|---|
| super_admin 全通 | `{role: super_admin, scope: None}` | hciot | True |
| admin 跨 app | `{role: admin, scope: jti}` | hciot | True |
| user 同 scope | `{role: user, scope: hciot}` | hciot | True |
| user 跨 scope | `{role: user, scope: hciot}` | jti | False |
| 未知 role | `{role: guest}` | hciot | False |

整合測試（可選，視既有 test client 而定）：scope user 對自己 app 的 knowledge files 端點回 200、對別 app 回 403。

## 6. 非目標（YAGNI）

- 不改 `verify_auth` / 登入流程 / user_manager。
- 不放寬對話歷史（conversations）。
- 不處理 general（動態多店、以 store_name 為 key，scope 語義不同）——若日後需要另開設計。
- 不做端點層級的細分讀/寫權限（user 同 scope 即可讀寫該 app 知識庫全部）。
