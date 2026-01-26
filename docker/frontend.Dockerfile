FROM node:20-alpine

WORKDIR /app

# 安裝 nginx
RUN apk add --no-cache nginx && \
    mkdir -p /var/lib/nginx/tmp/client_body /run/nginx /app/node_modules /app/dist && \
    chown -R node:node /app

# 複製 nginx 配置
COPY docker/nginx.conf /etc/nginx/http.d/default.conf

# 創建啟動腳本
RUN echo '#!/bin/sh' > /start.sh && \
    echo 'nginx' >> /start.sh && \
    echo 'cd /app && su node -c "npm install && npm run dev -- --host 0.0.0.0"' >> /start.sh && \
    chmod +x /start.sh

EXPOSE 5174 8008

CMD ["/start.sh"]
