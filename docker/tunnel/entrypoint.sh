#!/bin/sh
# db-tunnel entrypoint — 自動判斷環境，提供統一的 DocumentDB 連線埠 (27017)
#
# 行為：
#   - VPC 內（如 hciot 正式機 / 跳板本身）：能直接連到 DocumentDB endpoint
#       → 用 socat 純 TCP 轉發 27017 → endpoint:27017（不需 SSH、不需金鑰）
#   - VPC 外（如開發機）：連不到 endpoint
#       → 用 autossh 經跳板建立 SSH tunnel（需要 bastion_key）
#
# 不論哪種情境，backend 都固定連 db-tunnel:27017，無需知道自己身在何處。
set -eu

# ---- 必要環境變數 ----
: "${DOCDB_ENDPOINT:?需設定 DOCDB_ENDPOINT}"
DOCDB_PORT="${DOCDB_PORT:-27017}"
LISTEN_PORT="${LISTEN_PORT:-27017}"

# 跳板（VPC 外才會用到）
BASTION_HOST="${BASTION_HOST:-52.12.0.227}"
BASTION_USER="${BASTION_USER:-ec2-user}"
BASTION_KEY="${BASTION_KEY:-/id_rsa}"

# 直連探測逾時：寫死 10s。搬遷初期網路未知時，5s 偏緊易誤判成「連不到」
# 而退去走 SSH tunnel，但目標機（VPC 內）未必放 bastion_key → 容器 exit 1 起不來。
# VPC 內直連通常 <1s，多等的秒數只在真的連不到時才發生，對正常啟動無感。
PROBE_TIMEOUT="${PROBE_TIMEOUT:-10}"

log() {
    echo "[db-tunnel] $*"
}

can_reach_docdb() {
    nc -z -w "${PROBE_TIMEOUT}" "${DOCDB_ENDPOINT}" "${DOCDB_PORT}" 2>/dev/null
}

# 持久化目前模式供 healthcheck.sh 判據（direct=VPC 內 socat / ssh=VPC 外 autossh）。
MODE_FILE="/tmp/tunnel_mode"

start_direct_proxy() {
    log "✅ 可直連（VPC 內）→ 使用 socat TCP 轉發，不經跳板"
    echo "direct" > "${MODE_FILE}"
    exec socat -d "TCP-LISTEN:${LISTEN_PORT},fork,reuseaddr,bind=0.0.0.0" \
                  "TCP:${DOCDB_ENDPOINT}:${DOCDB_PORT}"
}

start_bastion_tunnel() {
    log "✗ 無法直連（VPC 外）→ 經跳板 ${BASTION_USER}@${BASTION_HOST} 建立 SSH tunnel"
    echo "ssh" > "${MODE_FILE}"
    if [ ! -f "${BASTION_KEY}" ]; then
        echo "[db-tunnel] ❌ 找不到金鑰 ${BASTION_KEY}（VPC 外必須掛載 bastion_key）" >&2
        exit 1
    fi

    chmod 600 "${BASTION_KEY}" 2>/dev/null || true
    exec autossh -M 0 -N \
        -o "StrictHostKeyChecking=accept-new" \
        -o "UserKnownHostsFile=/known_hosts" \
        -o "IdentitiesOnly=yes" \
        -o "ServerAliveInterval=30" \
        -o "ServerAliveCountMax=3" \
        -o "ExitOnForwardFailure=yes" \
        -i "${BASTION_KEY}" \
        -L "0.0.0.0:${LISTEN_PORT}:${DOCDB_ENDPOINT}:${DOCDB_PORT}" \
        "${BASTION_USER}@${BASTION_HOST}"
}

log "探測是否可直連 DocumentDB: ${DOCDB_ENDPOINT}:${DOCDB_PORT} (timeout ${PROBE_TIMEOUT}s)"

if can_reach_docdb; then
    start_direct_proxy
fi

start_bastion_tunnel
