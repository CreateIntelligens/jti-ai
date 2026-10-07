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

# 直接以 --chown 複製：事後 chown -R 會把整個 torch venv 再寫一層（十多分鐘、I/O 打滿），
# 而且放在 app.py 之後，改一行程式就得重跑。
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

WORKDIR /app
RUN mkdir -p /home/appuser/.cache/huggingface \
    && chown appuser:appuser /app /home/appuser/.cache /home/appuser/.cache/huggingface
COPY --chmod=755 docker/embedding/entrypoint.sh /usr/local/bin/embedding-entrypoint.sh
COPY --chown=appuser:appuser docker/embedding/app.py /app/app.py

ENTRYPOINT ["/usr/local/bin/embedding-entrypoint.sh"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8009"]
