# uv 容器安裝移植 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 backend 與 embedding 兩個容器的依賴安裝從 pip（heredoc/`requirements/*.txt`）改為 `uv sync --frozen`，使 `pyproject.toml` + `uv.lock` 成為唯一依賴事實來源。

**Architecture:** 重整 pyproject 的 dependency-groups（pytest 移入 dev group），兩個 Dockerfile 改用官方 `uv` binary 在 builder stage 跑 `uv sync --frozen` 裝進 `.venv`，再 copy `.venv` 進 runner；刪除所有 pip requirements 檔。維持 multi-stage builder→runner、appuser 非 root、entrypoint/compose 拓樸不變。

**Tech Stack:** uv 0.11.21、Python 3.12-slim、Docker multi-stage、docker compose、pytest。

## Global Constraints

- 所有 docker 操作 **cd 到 `~/jtai/.worktrees/jtai-rag`** 再執行；容器名跟目錄（`jtai-rag-*`）。
- Heavy build 守則（CLAUDE.md）：**一次一個 build、絕不並行、build 與 run 分離**；torch heavy build 單獨跑完再起服務。
- build 時可連網；版本一律照 `uv.lock`，**不升級任何套件**。
- 依賴範圍：backend = 主 deps + `backend-heavy`（無 dev、無 torch）；embedding = `--only-group embedding --only-group embedding-heavy`（無主 deps）。
- runner OS 套件、appuser UID/GID 1000、HF_HOME、entrypoint、CMD、compose 服務拓樸、nginx 路由 **一律不動**。
- uv 版本 pin：`ghcr.io/astral-sh/uv:0.11.21`（與 host 一致）。
- 對外測 API 打 **8913**（經 nginx）；容器內 backend `:8008`、embedding `:8009`。

---

### Task 1: 重整 pyproject 並重鎖 lock

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`（由 `uv lock` 產生）

**Interfaces:**
- Produces：穩定的 dependency-groups — 主 `dependencies`（不含 pytest）、`backend-heavy`、`embedding`（含 fastapi+uvicorn[standard]）、`embedding-heavy`、`dev`（pytest+pytest-mock）。後續 Dockerfile task 依賴這些 group 名。

- [ ] **Step 1: 把 pytest/pytest-mock 從主 dependencies 移到 dev group**

編輯 `pyproject.toml`：主 `dependencies` 陣列刪掉 `"pytest>=9.1.1"` 與 `"pytest-mock>=3.15.1"` 兩行；在 `[dependency-groups]` 末尾新增：

```toml
dev = [
    "pytest>=9.1.1",
    "pytest-mock>=3.15.1",
]
```

`embedding` group 維持含 fastapi（`--only-group` 不帶主 deps，app.py 需要）：

```toml
embedding = [
    "fastapi>=0.138.1",
    "uvicorn[standard]>=0.49.0",
]
```

- [ ] **Step 2: 重鎖 lock 並驗證**

Run:
```bash
cd ~/jtai/.worktrees/jtai-rag
uv lock
uv lock --check
```
Expected: `uv lock --check` 印 `Resolved N packages`、無錯誤、exit 0。

- [ ] **Step 3: 驗證三個 sync 範圍解得開（dry-run，不動 venv）**

Run:
```bash
uv sync --frozen --no-default-groups --group backend-heavy --dry-run
uv sync --frozen --no-default-groups --only-group embedding --only-group embedding-heavy --dry-run
uv sync --frozen --dry-run
```
Expected: 三條都成功、無 resolution error。第二條的輸出含 `torch`、不含 `google-genai`。

- [ ] **Step 4: host venv sync 全 groups（給後續 pytest 用）**

Run:
```bash
uv sync --frozen
uv run python -c "import pytest, fastapi, lancedb, google.genai; print('ok')"
```
Expected: 印 `ok`。

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "refactor: move pytest to dev group, relock for uv container install"
```

---

### Task 2: backend Dockerfile 改用 uv sync

**Files:**
- Modify: `docker/backend/Dockerfile`

**Interfaces:**
- Consumes：Task 1 的 `backend-heavy` group 與不含 pytest 的主 deps。
- Produces：backend image 內 `/app/.venv` 含主 deps + numpy/pandas，`uvicorn` 在 PATH 上。

- [ ] **Step 1: 改寫 Dockerfile 為 uv sync 架構**

把 `docker/backend/Dockerfile` 整檔改為（保留 runner 的 OS 套件/appuser/entrypoint 區塊原樣）：

```dockerfile
# syntax=docker/dockerfile:1.7

# ---------- builder ----------
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# 只 copy lock 元資料 → 依賴層與 app 原始碼解耦，命中 build cache。
# backend 範圍：主 deps + backend-heavy（numpy/pandas），不含 dev/torch。
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-default-groups --group backend-heavy

# ---------- runner ----------
FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BACKEND_PORT=8008 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgomp1 \
        gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 appuser \
    && useradd -m -u 1000 -g appuser appuser

COPY --from=builder /app/.venv /app/.venv

WORKDIR /app
RUN mkdir -p /app/data/lancedb /app/logs /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /app /home/appuser/.cache

COPY docker/backend/entrypoint.sh /usr/local/bin/backend-entrypoint.sh
RUN chmod +x /usr/local/bin/backend-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/backend-entrypoint.sh"]
# 不帶 CMD：entrypoint 依 $MODE 決定 uvicorn 參數（dev=--reload / prod=--workers）
```

- [ ] **Step 2: build backend（單獨、完整跑完）**

Run:
```bash
cd ~/jtai/.worktrees/jtai-rag
docker compose build backend
```
Expected: build 成功；uv sync 那層出現解析/安裝、無 error。

- [ ] **Step 3: 驗證 image 內依賴正確（含主 deps、不含 pytest/torch）**

Run:
```bash
docker compose run --rm --no-deps --entrypoint sh backend -c \
  'python -c "import fastapi, lancedb, google.genai, numpy, pandas; print(\"deps ok\")" && \
   python -c "import pytest" 2>&1 | tail -1; \
   python -c "import torch" 2>&1 | tail -1'
```
Expected: 印 `deps ok`；接著兩行 `ModuleNotFoundError`（pytest 與 torch 都不在 image 內，符合範圍收斂）。

- [ ] **Step 4: Commit**

```bash
git add docker/backend/Dockerfile
git commit -m "feat: backend Dockerfile installs deps via uv sync from lock"
```

---

### Task 3: embedding Dockerfile 改用 uv sync

**Files:**
- Modify: `docker/embedding/Dockerfile`

**Interfaces:**
- Consumes：Task 1 的 `embedding` + `embedding-heavy` groups。
- Produces：embedding image `/app/.venv` 含 torch/transformers/fastapi 那批、**不含** google-genai/pymongo/lancedb。

- [ ] **Step 1: 改寫 Dockerfile 為 uv sync 架構**

把 `docker/embedding/Dockerfile` 整檔改為（保留 runner 的 OS 套件/appuser/HF_HOME/app.py copy/entrypoint/CMD 原樣）：

```dockerfile
# syntax=docker/dockerfile:1.7

# ---------- builder ----------
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# embedding 範圍：只裝 embedding + embedding-heavy（torch 那批 + fastapi/uvicorn），
# 不裝主 deps。query 端與 backfill 端必須同模型同版本，由 uv.lock 保證單一版本。
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-default-groups \
        --only-group embedding --only-group embedding-heavy

# ---------- runner ----------
FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/appuser/.cache/huggingface \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgomp1 \
        gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 appuser \
    && useradd -m -u 1000 -g appuser appuser

COPY --from=builder /app/.venv /app/.venv

WORKDIR /app
COPY docker/embedding/app.py /app/app.py
COPY docker/embedding/entrypoint.sh /usr/local/bin/embedding-entrypoint.sh
RUN chmod +x /usr/local/bin/embedding-entrypoint.sh \
    && mkdir -p /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /app /home/appuser/.cache

ENTRYPOINT ["/usr/local/bin/embedding-entrypoint.sh"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8009"]
```

- [ ] **Step 2: build embedding（單獨、完整跑完、heavy build 不並行）**

確認沒有其他 build 在跑，再執行：
```bash
cd ~/jtai/.worktrees/jtai-rag
docker compose build embedding
```
Expected: build 成功（torch 等大套件下載/安裝可能數分鐘）；uv sync 層無 error。

- [ ] **Step 3: 驗證 image 範圍隔離（含 torch、不含 google-genai/lancedb）**

Run:
```bash
docker compose run --rm --no-deps --entrypoint sh embedding -c \
  'python -c "import torch, transformers, fastapi, sentence_transformers; print(\"emb ok\")" && \
   python -c "import google.genai" 2>&1 | tail -1; \
   python -c "import lancedb" 2>&1 | tail -1'
```
Expected: 印 `emb ok`；接著兩行 `ModuleNotFoundError`（google.genai 與 lancedb 不在 embedding image，證明 `--only-group` 隔離正確）。

- [ ] **Step 4: Commit**

```bash
git add docker/embedding/Dockerfile
git commit -m "feat: embedding Dockerfile installs deps via uv sync only-group"
```

---

### Task 4: 刪除 pip requirements 來源檔

**Files:**
- Delete: `requirements.txt`
- Delete: `requirements/backend-heavy/requirements.txt`、`requirements/embedding-heavy/requirements.txt`、`requirements/` 目錄
- Delete: `docker/embedding/requirements.txt`

**Interfaces:**
- Consumes：Task 2、3 已不再引用任何 requirements 檔。

- [ ] **Step 1: 確認 Dockerfile 已不引用 requirements 檔**

Run:
```bash
cd ~/jtai/.worktrees/jtai-rag
grep -rn "requirements" docker/backend/Dockerfile docker/embedding/Dockerfile || echo "no refs"
```
Expected: 印 `no refs`（兩個 Dockerfile 都不再提 requirements）。

- [ ] **Step 2: 刪除檔案**

Run:
```bash
git rm requirements.txt docker/embedding/requirements.txt
git rm -r requirements/
```
Expected: git 標記三組刪除。

- [ ] **Step 3: 確認沒有其他地方引用這些檔**

Run:
```bash
grep -rn "requirements/backend-heavy\|requirements/embedding-heavy\|requirements.txt" \
  --include="*.sh" --include="Dockerfile" --include="*.yml" --include="*.yaml" \
  docker/ docker-compose.yml scripts/ 2>/dev/null || echo "clean"
```
Expected: 印 `clean`（或僅命中註解，無實際引用）。若命中 entrypoint/script 實際引用，需一併修掉再繼續。

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: drop pip requirements files, uv.lock is single source"
```

---

### Task 5: 起服務 + 煙霧測試 + pytest 綠

**Files:**（無修改，純驗證）

**Interfaces:**
- Consumes：Task 2、3 的 image。

- [ ] **Step 1: 起整個 stack**

Run:
```bash
cd ~/jtai/.worktrees/jtai-rag
docker compose up -d
```
Expected: 各服務 Created/Started、無 build（image 已存在）。

- [ ] **Step 2: 等並確認 embedding 與 backend healthy**

Run（等 healthcheck，embedding start_period 120s、backend 300s）:
```bash
sleep 30; docker compose ps
```
Expected: `embedding` 與 `backend` 狀態趨向 `healthy`（首次可能 starting；可重跑 ps 觀察）。

- [ ] **Step 3: embedding /health 探活**

Run:
```bash
docker compose exec -T embedding python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:8009/health').status)"
```
Expected: 印 `200`。

- [ ] **Step 4: backend /health 探活（容器內 + 經 nginx 對外 8913）**

Run:
```bash
docker compose exec -T backend python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:8008/health').status)"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8913/api/health 2>/dev/null || echo "nginx路徑視實際 /api 前綴調整"
```
Expected: 容器內印 `200`；對外 8913 若 nginx 已起則 `200`（路徑前綴依實際 nginx 設定，非本任務重點）。

- [ ] **Step 5: host 跑既有 pytest suite**

Run:
```bash
cd ~/jtai/.worktrees/jtai-rag
uv run pytest -q
```
Expected: 全綠（或僅有與本次無關的既有已知 skip/xfail）。若有 import error 與依賴相關，回 Task 1 檢查 group 範圍。

- [ ] **Step 6: 標記計畫完成（待用戶確認後改設計文件狀態）**

確認上述全綠後，回報用戶；經用戶確認再把設計文件 `## 狀態` 由 Draft 改 Done。

## Self-Review

- **Spec coverage**：§2 pyproject 重整→Task 1；§3 兩 Dockerfile→Task 2/3；§4 清理→Task 4；§5 驗證（build+起服務+import 隔離+pytest）→Task 2/3 Step3 與 Task 5。全覆蓋。
- **Placeholder scan**：無 TBD/TODO；每個 code/command step 都有實際內容。Task 4 Step3 與 Task 5 Step4 的 nginx 路徑明確標為「視實際設定」屬合理彈性，非佔位。
- **Type consistency**：group 名稱（`backend-heavy`/`embedding`/`embedding-heavy`/`dev`）、sync 旗標（`--no-default-groups`/`--group`/`--only-group`）、路徑（`/app/.venv`）跨任務一致。
