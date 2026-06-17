#!/bin/sh
set -e

# 未帶 command（$# = 0）時用 MODE 推導；有帶就尊重呼叫端覆寫。
if [ "$#" -eq 0 ]; then
    PORT="${BACKEND_PORT:-${PORT:-8008}}"
    MODE="${MODE:-prod}"

    case "$MODE" in
        dev)
            echo "[entrypoint] MODE=dev → uvicorn --reload (port $PORT)" >&2
            set -- uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
            ;;
        prod)
            # 預設單 worker：session 的 _pending lazy-write 為 process 內記憶體，多 worker 會跨 process
            # 失憶（/chat/start 與 /chat/message 打到不同 worker → 404）。待 session 狀態改為共享
            # (寫 Mongo / TTL) 後，可在 .env 設 UVICORN_WORKERS=2 恢復多 worker。
            WORKERS="${UVICORN_WORKERS:-2}"
            echo "[entrypoint] MODE=prod → uvicorn --workers $WORKERS (port $PORT)" >&2
            set -- uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers "$WORKERS"
            ;;
        *)
            echo "[entrypoint] MODE must be 'dev' or 'prod' (got '$MODE')" >&2
            exit 2
            ;;
    esac
fi

if [ "$(id -u)" = "0" ]; then
    # 修復 volume 權限：appuser 是 UID/GID 1000，掛載進來的 host 目錄物主須對齊，
    # 否則降權後寫不了 log / data。失敗不再靜默吞掉——印出來方便定位被污染的檔。
    if ! chown -R 1000:1000 /app/data /app/logs /home/appuser/.cache; then
        echo "[entrypoint] 警告：chown /app/data /app/logs 部分失敗，" \
             "可能有檔案被 root 或其他 UID 污染，appuser 將無法寫入。" >&2
    fi
    exec gosu appuser "$@"
fi

exec "$@"
