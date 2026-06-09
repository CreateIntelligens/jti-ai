# db-tunnel — DocumentDB 連線中繼容器

讓 backend 在**任何環境**都用同一個位址 `db-tunnel:27017` 連到 AWS DocumentDB，
容器啟動時自動判斷該直連還是走跳板，無需為不同機器準備不同設定或指令。

## 運作方式

容器啟動時探測能否直連 DocumentDB endpoint：

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
ssh-keygen -t ed25519 -f docker/tunnel/bastion_key -C "jtai-$(hostname)-to-bastion" -N ""
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

## 環境變數（compose 中設定）

| 變數 | 預設 | 說明 |
|---|---|---|
| `DOCDB_ENDPOINT` | （必填） | DocumentDB cluster endpoint |
| `DOCDB_PORT` | 27017 | DocumentDB 連接埠 |
| `LISTEN_PORT` | 27017 | 容器對 backend 開放的埠 |
| `BASTION_HOST` | 52.12.0.227 | 跳板機（VPC 外才用） |
| `BASTION_USER` | ec2-user | 跳板登入帳號 |
| `BASTION_KEY` | /id_rsa | 容器內金鑰路徑（由 volume 掛入） |
| `PROBE_TIMEOUT` | 5 | 直連探測逾時秒數 |
