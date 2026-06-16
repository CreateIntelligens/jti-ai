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
            echo "[entrypoint] MODE=prod → uvicorn --workers 2 (port $PORT)" >&2
            set -- uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 2
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
