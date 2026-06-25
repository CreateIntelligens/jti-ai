#!/bin/sh
set -e

if [ "$(id -u)" = "0" ]; then
    # 修復 .hf_cache mount 權限：appuser 是 UID/GID 1000，掛載進來的 host 目錄物主須對齊，
    # 否則降權後 HuggingFace 寫不了模型快取。失敗印出來方便定位被污染的檔。
    if ! chown -R 1000:1000 /home/appuser/.cache; then
        echo "[entrypoint] 警告：chown /home/appuser/.cache 部分失敗，" \
             "可能有檔案被 root 或其他 UID 污染，appuser 將無法寫入。" >&2
    fi
    exec gosu appuser "$@"
fi

exec "$@"
