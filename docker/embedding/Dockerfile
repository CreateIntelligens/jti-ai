# syntax=docker/dockerfile:1.7

# ---------- Stage 1: builder ----------
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

# ---- 重 & 穩定相依（ML/RAG）：版本鎖死、極少變動 ----
# 與 docker/backend.Dockerfile 逐字一致：query 端與 backfill 端必須同模型同版本，
# 否則向量空間錯位、檢索靜默回錯結果。獨立成一層命中 build cache。
COPY <<EOF embedding-heavy-requirements.txt
torch==2.5.1
transformers==4.46.3
accelerate==0.34.2
sentence-transformers==3.3.1
FlagEmbedding==1.3.5
numpy==2.4.6
EOF

RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir=/wheels -r embedding-heavy-requirements.txt

COPY docker/embedding/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir=/wheels -r requirements.txt

# ---------- Stage 2: deps ----------
FROM python:3.12-slim AS deps

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY --from=builder /wheels /wheels
COPY --from=builder /build/embedding-heavy-requirements.txt /tmp/embedding-heavy-requirements.txt
COPY --from=builder /build/requirements.txt /tmp/requirements.txt
# /wheels may contain multiple versions of the same transitive package when
# cached layers were built at different times. Install requirement roots from
# the local wheelhouse so pip resolves one compatible candidate.
RUN pip install --no-index --find-links=/wheels --prefix=/install \
        -r /tmp/embedding-heavy-requirements.txt \
        -r /tmp/requirements.txt \
    && rm -rf /wheels /tmp/embedding-heavy-requirements.txt /tmp/requirements.txt

# ---------- Stage 3: runner ----------
FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/appuser/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgomp1 \
        gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 appuser \
    && useradd -m -u 1000 -g appuser appuser

COPY --from=deps /install /usr/local

WORKDIR /app
COPY docker/embedding/app.py /app/app.py
COPY docker/embedding/entrypoint.sh /usr/local/bin/embedding-entrypoint.sh
RUN chmod +x /usr/local/bin/embedding-entrypoint.sh \
    && mkdir -p /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /app /home/appuser/.cache

ENTRYPOINT ["/usr/local/bin/embedding-entrypoint.sh"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8009"]
