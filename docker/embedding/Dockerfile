# syntax=docker/dockerfile:1.7

# ---------- builder ----------
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# embedding 範圍：只裝 embedding + embedding-heavy（torch 那批 + fastapi/uvicorn），
# 不裝主 deps。query 端與 backfill 端必須同模型同版本，否則向量空間錯位、檢索
# 靜默回錯結果——版本由 uv.lock 保證單一來源、單一版本。
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
