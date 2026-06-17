#!/bin/sh
# db-tunnel healthcheck — 模式感知端到端探活
#
# 舊版只做 `nc -z localhost 27017`，僅確認轉發進程在 listen，無法偵測
# 「socat/autossh 還活著但後端隧道已斷」的卡住狀態（健康假象 → Docker 不 restart）。
# 改為依 entrypoint 寫下的模式做真正能反映後端可達性的探測：
#   - direct (VPC 內 socat)：直接 nc 探 DocDB endpoint；後端斷 → 探測失敗。
#   - ssh    (VPC 外 autossh)：endpoint 本不可達，改驗 autossh 進程存活
#       （autossh 帶 ExitOnForwardFailure，隧道死會退出）+ localhost 仍 listen。
set -eu

DOCDB_ENDPOINT="${DOCDB_ENDPOINT:?}"
DOCDB_PORT="${DOCDB_PORT:-27017}"
LISTEN_PORT="${LISTEN_PORT:-27017}"
HC_TIMEOUT="${HC_TIMEOUT:-5}"
MODE_FILE="/tmp/tunnel_mode"

# 模式檔尚未寫出（容器剛啟動，start_period 內）→ 視為尚在初始化，回非健康讓其等待。
[ -f "${MODE_FILE}" ] || { echo "mode file 尚未就緒"; exit 1; }
MODE="$(cat "${MODE_FILE}")"

case "${MODE}" in
    direct)
        # VPC 內：直接探 DocumentDB endpoint，確認 socat 後端目標仍可達。
        if nc -z -w "${HC_TIMEOUT}" "${DOCDB_ENDPOINT}" "${DOCDB_PORT}" 2>/dev/null; then
            exit 0
        fi
        echo "direct 模式：無法連到 ${DOCDB_ENDPOINT}:${DOCDB_PORT}（後端不可達）"
        exit 1
        ;;
    ssh)
        # VPC 外：endpoint 不可達，驗 autossh 進程存活（隧道死會退出）+ 本地 listen。
        if ! pgrep -f autossh >/dev/null 2>&1; then
            echo "ssh 模式：autossh 進程不存在（隧道已斷）"
            exit 1
        fi
        if ! nc -z -w "${HC_TIMEOUT}" localhost "${LISTEN_PORT}" 2>/dev/null; then
            echo "ssh 模式：localhost:${LISTEN_PORT} 未在 listen"
            exit 1
        fi
        exit 0
        ;;
    *)
        echo "未知模式: ${MODE}"
        exit 1
        ;;
esac
