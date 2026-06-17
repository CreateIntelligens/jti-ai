# db-tunnel — 自動判斷環境的 DocumentDB 連線中繼容器
# VPC 內用 socat 直連轉發；VPC 外用 autossh 經跳板建立 SSH tunnel。
FROM alpine:3.20 AS runner

# socat: VPC 內 TCP 轉發；openssh + autossh: VPC 外 SSH tunnel；netcat: 環境探測
RUN apk add --no-cache socat openssh-client autossh netcat-openbsd

COPY docker/tunnel/entrypoint.sh /entrypoint.sh
COPY docker/tunnel/healthcheck.sh /healthcheck.sh
RUN chmod +x /entrypoint.sh /healthcheck.sh

# DocumentDB 連線埠（backend 連這個容器的 27017）
EXPOSE 27017

ENTRYPOINT ["/entrypoint.sh"]
