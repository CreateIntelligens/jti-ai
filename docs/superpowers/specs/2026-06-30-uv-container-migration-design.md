# 設計：backend + embedding 容器安裝完整轉 uv

- **狀態**：Draft
- **日期**：2026-06-30
- **範圍**：`~/jtai/.worktrees/jtai-rag`（branch `feat/rag`）
- **目標**：消滅「pip 裝（heredoc / `requirements/*.txt`）＋ uv 管 `uv.lock`」的雙來源，讓
  `pyproject.toml` + `uv.lock` 成為唯一事實來源；兩個 Dockerfile 改用 `uv sync --frozen`
  從 lock 直裝 `.venv`，build 時可連網、靠 lock 保證可重現。

## 1. 現況（為何要做）

依賴版本目前同時存在於三個地方，須人工同步：

| 來源 | 內容 | 問題 |
|------|------|------|
| `docker/*/Dockerfile`（原 heredoc，已被前一步抽成檔案） | heavy 套件 pin | 與 pyproject 手抄重複 |
| `requirements.txt` + `requirements/*/requirements.txt` | backend 全依賴 | 與 pyproject 手抄重複 |
| `pyproject.toml` + `uv.lock` | groups 完整定義 | 真正可重現，但 **build 不讀它** |

前一步已把 heredoc 抽成 `requirements/{backend-heavy,embedding-heavy}/requirements.txt`，
但那仍是手抄清單、pip 流程未動，本質沒解決雙來源。

實測事實（已驗證）：
- host `uv 0.11.21`，`uv lock --check` 通過（120 packages，lock 與 pyproject 一致）。
- backend 與 embedding **共用 `numpy==2.4.6`**（backend-heavy 與 embedding-heavy 都列）；
  lock 已解析成單一版本——轉 uv 後天然消除漂移。
- `uv sync --no-default-groups --group backend-heavy` → 57 packages（主 deps 去 pytest + numpy/pandas）。
- `uv sync --no-default-groups --only-group embedding --only-group embedding-heavy`
  → 正確算出 torch/transformers/… 的隔離集，**不含** google-genai/pymongo/lancedb。

## 2. pyproject 重整（依賴範圍收斂）

「完整收斂」而非 1:1 搬遷。重整後：

```toml
[project]
dependencies = [
    # 執行期：google-genai, python-dotenv, fastapi, uvicorn, python-multipart,
    # pymongo, redis, openpyxl, pydantic, pydantic-settings,
    # opencc-python-reimplemented, lancedb, httpx, bcrypt, PyJWT, cryptography
    # （移除 pytest / pytest-mock → 改入 dev group）
]

[dependency-groups]
backend-heavy   = ["numpy==2.4.6", "pandas==3.0.3"]
embedding       = ["fastapi>=0.138.1", "uvicorn[standard]>=0.49.0"]   # --only-group 不帶主 deps，須自列 fastapi
embedding-heavy = ["torch==2.5.1", "transformers==4.46.3", "accelerate==0.34.2",
                   "sentence-transformers==3.3.1", "FlagEmbedding==1.3.5", "numpy==2.4.6"]
dev             = ["pytest>=9.1.1", "pytest-mock>=3.15.1"]
```

變更點：
1. **`pytest` / `pytest-mock` 從主 `dependencies` → `dev` group**。後果：backend runner image
   不再含 pytest。容器內 `docker exec ... pytest` 不再可用；改以 **host `uv run pytest`** 驗證
   （host `.venv` sync 全 groups）。compose 仍把 `./tests` 掛進容器，但測試執行點移到 host。
2. **`embedding` group 保留 `fastapi` 與 `uvicorn[standard]`**。理由：embedding 用 `--only-group`
   （刻意不裝主 deps），而 `app.py` 跑 `app:app` 需要 fastapi；若只靠主 deps 的 fastapi，
   `--only-group` 會把它排除掉。故 fastapi 必須留在 embedding group 內（與主 deps 重複宣告無害，
   lock 解析為單一版本）。
3. 改動 pyproject 後執行 `uv lock`（連網重解析），commit 新 `uv.lock`。

各服務 sync 範圍（最終）：
- **backend** = `uv sync --frozen --no-default-groups --group backend-heavy`
  （= 主 deps + numpy/pandas，無 dev、無 torch）
- **embedding** = `uv sync --frozen --no-default-groups --only-group embedding --only-group embedding-heavy`
  （= fastapi/uvicorn + torch 那批，**無** 主 deps）
- **dev / CI（host）** = `uv sync --frozen`（預設裝主 deps + 全 groups 含 dev）

## 3. Dockerfile 架構（兩檔同型）

維持 multi-stage `builder → runner`，但安裝改 `uv sync`。採 uv 官方 distroless 思路的精簡版：

```dockerfile
# ---------- builder ----------
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# 先只 copy lock 元資料 → 裝依賴層（命中 cache，不受 app 原始碼變動影響）
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-default-groups <服務專屬 group 旗標>

# ---------- runner ----------
FROM python:3.12-slim AS runner
# ...（既有：ca-certificates / libgomp1 / gosu、建 appuser UID/GID 1000、HF_HOME 等不變）
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
# entrypoint 不變（uvicorn 已在 .venv/bin/PATH 上）
```

關鍵點：
- **不再有 `deps` 中間 stage / `/install` prefix / `/wheels`**；改為直接 copy `.venv`。
- `--no-install-project`：只裝依賴，不把專案自身當套件裝（app 原始碼由 compose volume 掛入，
  與現況一致）。依賴層與原始碼解耦 → cache 命中率高。
- `UV_PYTHON_DOWNLOADS=0`：禁止 uv 自抓 Python，用 base image 的 3.12（與現況一致）。
- **backend** builder 旗標：`--group backend-heavy`
- **embedding** builder 旗標：`--only-group embedding --only-group embedding-heavy`
- runner 的 OS 套件、appuser、HF_HOME、entrypoint、CMD **全部不動**——只換「依賴怎麼進 image」。

## 4. 清理（單一事實來源落地）

轉成後刪除已無來源價值的檔案：
- `requirements.txt`
- `requirements/backend-heavy/requirements.txt`、`requirements/embedding-heavy/requirements.txt`
  及 `requirements/` 目錄
- `docker/embedding/requirements.txt`

唯一依賴事實來源 = `pyproject.toml` + `uv.lock`。

## 5. 驗證（成功標準：build + 起服務 + pytest 綠）

遵守 CLAUDE.md heavy-build 守則：**一次一個 build、不並行、build 與 run 分離**。

1. `uv lock` 後 `uv sync --frozen`（host）→ 確認 lock 解得開。
2. `docker compose build backend`（先，較輕）→ 完整跑完。
3. `docker compose build embedding`（後，含 torch 重 build）→ 單獨、完整跑完。
4. `docker compose up -d` → 等 healthcheck。
5. 煙霧測試：
   - embedding `/health`（容器內 `:8009`）活。
   - backend `/health` 活（經 nginx 對外打 **8913**，或容器內 `:8008`）。
   - 確認 embedding image **不含** google-genai（`uv pip list` 或 import 檢查），證明範圍隔離正確。
6. host `uv run pytest`（worktree 根）→ 綠，確認轉 uv 沒裝壞依賴。

## 6. 風險與回滾

- **風險**：embedding `--only-group` 漏掉某個主 deps 才有的 runtime 依賴 → `app.py` import 失敗。
  緩解：步驟 5 的 import 檢查 + `/health` 探活會立刻抓到。
- **風險**：torch heavy build I/O 鎖死（CLAUDE.md 已知坑）。緩解：build 與 backend 分離、序列化、
  絕不並行；用 uv cache mount 降低重複下載。
- **回滾**：所有改動在 `feat/rag` worktree、未 commit 前 `git checkout` 即還原；Dockerfile/requirements
  改動可逐檔 revert。

## 7. 不做（YAGNI）

- 不做離線 wheelhouse / `--offline`（build 可連網已確認）。
- 不動 frontend / tunnel / redis 容器。
- 不改 entrypoint、compose 服務拓樸、nginx 路由。
- 不順手升級任何套件版本（純換安裝工具，版本一律照 lock）。
