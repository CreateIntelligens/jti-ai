FROM python:3.12-slim

# 創建非 root 用戶
RUN groupadd -g 1000 appuser && \
    useradd -m -u 1000 -g appuser appuser

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl-dev \
    libgomp1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 預先建立掛載目標目錄，確保 appuser 有寫入權限
RUN mkdir -p /app/data/lancedb /app/logs /home/appuser/.cache/huggingface && \
    chown -R appuser:appuser /app /home/appuser/.cache

# 切換到非 root 用戶
USER appuser

ENV BACKEND_PORT=8008
CMD uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT} --workers 1
