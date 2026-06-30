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
# torch / transformers / FlagEmbedding 等 GPU embedding 相依在獨立的 embedding
# 服務（docker/embedding/）；backend 經 HTTP 呼叫，不載模型。
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
# 不帶 CMD：entrypoint 依 $MODE 決定 uvicorn 參數（dev=--reload / prod=--workers 2）
