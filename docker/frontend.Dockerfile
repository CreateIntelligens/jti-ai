FROM node:20-alpine

WORKDIR /app

# 安裝 nginx 和 envsubst (gettext)
RUN apk add --no-cache nginx gettext && \
    mkdir -p /var/lib/nginx/tmp/client_body /run/nginx /app/node_modules /app/dist && \
    chown -R node:node /app

# 複製 nginx 配置模板
COPY docker/nginx.conf.template /etc/nginx/nginx.conf.template

# 創建啟動腳本 - 用 envsubst 替換環境變數
RUN echo '#!/bin/sh' > /start.sh && \
    echo 'export PORT=${PORT:-8008}' >> /start.sh && \
    echo 'envsubst "\$PORT" < /etc/nginx/nginx.conf.template > /etc/nginx/http.d/default.conf' >> /start.sh && \
    echo 'nginx' >> /start.sh && \
    echo 'cd /app && su node -c "npm install && npm run dev -- --host 0.0.0.0"' >> /start.sh && \
    chmod +x /start.sh

# 注意：EXPOSE 只是文檔用途，實際端口由 docker-compose.yml 的 ports 控制

CMD ["/start.sh"]
