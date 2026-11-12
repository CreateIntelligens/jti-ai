# db-tunnel — MongoDB 主庫連線中繼容器

讓 backend 在**任何環境**都用同一個位址 `db-tunnel:27017` 連到 AWS VPC 內的自架 MongoDB 主庫
（2026-11 起取代 AWS DocumentDB），
容器啟動時自動判斷該直連還是走跳板，無需為不同機器準備不同設定或指令。

## 運作方式

容器啟動時探測能否直連主庫（`DOCDB_ENDPOINT:DOCDB_PORT`）：

| 環境 | 探測結果 | 行為 | 需要金鑰？ |
|---|---|---|---|
| VPC 內（如 hciot 正式機） | 可直連 | `socat` 純 TCP 轉發 → endpoint | ❌ 不需要 |
| VPC 外（如開發機） | 連不到 | `autossh` 經跳板建 SSH tunnel | ✅ 需要 `bastion_key` |

backend 永遠連 `db-tunnel:27017`，不需知道自己身在何處。

## 部署前準備

### VPC 內（正式機）
不需任何金鑰，直接 `docker compose up -d` 即可。

### VPC 外（開發機 / 其他地點）
需要連跳板的 SSH 私鑰：

```bash
# 方式 A：複製既有金鑰
cp /path/to/bastion_key docker/tunnel/bastion_key
chmod 600 docker/tunnel/bastion_key

# 方式 B：為這台機器產生專屬金鑰（建議，可單獨撤銷）
ssh-keygen -t ed25519 -f docker/tunnel/bastion_key -C "ai360-km-$(hostname)-to-bastion" -N ""
# 再把 docker/tunnel/bastion_key.pub 加到跳板機的 ~/.ssh/authorized_keys
```

`known_hosts`（跳板指紋）若不存在會自動接受首次連線；要預先固定可執行：
```bash
ssh-keyscan -t ed25519,rsa <跳板IP> > docker/tunnel/known_hosts
```

## 機密檔說明

| 檔案 | 進版控？ | 用途 |
|---|---|---|
| `Dockerfile`、`entrypoint.sh` | ✅ 是 | 容器邏輯 |
| `bastion_key.example` | ✅ 是 | 範本，說明金鑰怎麼放 |
| `bastion_key` | ❌ 否（.gitignore） | 實際私鑰 |
| `known_hosts` | ❌ 否（.gitignore） | 跳板指紋 |
| `mongodb-ca.crt` | ❌ 否（.gitignore） | 主庫 TLS CA，backend 經 `/app/docker/tunnel/mongodb-ca.crt` 讀取 |

## 環境變數（compose 中設定）

| 變數 | 預設 | 說明 |
|---|---|---|
| `DOCDB_ENDPOINT` | （必填） | MongoDB 主庫的內網位址（變數名沿用 DocumentDB 時期） |
| `DOCDB_PORT` | 27017 | 主庫連接埠（目前的自架主庫是 27018） |
| `LISTEN_PORT` | 27017 | 容器對 backend 開放的埠 |
| `BASTION_HOST` | 52.12.0.227 | 跳板機（VPC 外才用） |
| `BASTION_USER` | ec2-user | 跳板登入帳號 |
| `BASTION_KEY` | /id_rsa | 容器內金鑰路徑（由 volume 掛入） |
| `PROBE_TIMEOUT` | 10 | 直連探測逾時秒數 |

## TLS 與主機名稱

主庫憑證只簽給主庫自己的 IP（以及 `127.0.0.1`、`localhost`）。backend 用 `db-tunnel` 這個名稱連線，
所以 `MONGODB_URI` 要帶 `tlsAllowInvalidHostnames=true`；`tlsCAFile` 的 CA 驗證仍然有效。
