FROM python:3.12-slim

# 創建非 root 用戶
RUN groupadd -g 1000 appuser && \
    useradd -m -u 1000 -g appuser appuser

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 更改工作目錄擁有者
RUN chown -R appuser:appuser /app

# 切換到非 root 用戶
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8008"]
