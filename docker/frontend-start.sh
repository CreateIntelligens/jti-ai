#!/bin/sh
set -e

export PORT=${PORT:-8008}

# 生成 nginx 設定
envsubst "\$PORT" < /etc/nginx/nginx.conf.template > /etc/nginx/http.d/default.conf

# anonymous volume (/app/node_modules) 首次建立或再起容器時，
# 可能殘留 root 擁有的檔案，導致 npm install 時原子 rename 失敗（EACCES）。
# 這裡強制同步成 node owner，副作用比排查/重建 volume 小。
chown -R node:node /app/node_modules 2>/dev/null || true

nginx
cd /app
exec su node -c "npm install && npm run dev -- --host 0.0.0.0"
