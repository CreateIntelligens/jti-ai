FROM node:20-alpine

WORKDIR /app

# 安裝 nginx 和 envsubst (gettext)
RUN apk add --no-cache nginx gettext && \
    mkdir -p /var/lib/nginx/tmp/client_body /run/nginx /app/node_modules /app/dist && \
    chown -R node:node /app

# 複製 nginx 配置模板與啟動腳本
COPY docker/nginx.conf.template /etc/nginx/nginx.conf.template
COPY docker/frontend-start.sh /start.sh
RUN chmod +x /start.sh

# 注意：EXPOSE 只是文檔用途，實際端口由 docker-compose.yml 的 ports 控制

CMD ["/start.sh"]
