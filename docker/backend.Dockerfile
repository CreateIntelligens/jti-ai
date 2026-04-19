# syntax=docker/dockerfile:1.7

# ---------- Stage 1: builder ----------
# 編譯/產生 wheels（含 build toolchain，不進最終映像）
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libssl-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir=/wheels -r requirements.txt

# ---------- Stage 2: deps ----------
# 從 wheels 安裝到獨立 prefix，之後整包 copy 到 runner
FROM python:3.12-slim AS deps

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY --from=builder /wheels /wheels
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-index --find-links=/wheels --prefix=/install -r /tmp/requirements.txt \
    && rm -rf /wheels /tmp/requirements.txt

# ---------- Stage 3: runner ----------
# 最終 runtime：無 compiler、非 root、只帶執行期所需 lib
FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BACKEND_PORT=8008

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 appuser \
    && useradd -m -u 1000 -g appuser appuser

COPY --from=deps /install /usr/local

WORKDIR /app
RUN mkdir -p /app/data/lancedb /app/logs /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /app /home/appuser/.cache

USER appuser

CMD uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT} --workers 1
