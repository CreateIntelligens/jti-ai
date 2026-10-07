# Embedding 模型切換手冊

適用：本地 embedding profile（`COMPOSE_PROFILES=embedding`）的部署，從 BAAI/bge-m3 換成
EmbeddingGemma 2（`google/embeddinggemma-2`，768 維）。之後再換模型，步驟也一樣。

## 前置確認

- 這台機器有 GPU。gemma 約佔 3 GB；不停機切換時，舊模型（約 2.5 GB）會同時在跑。
- 可以連到 huggingface.co（第一次要下載模型，不需要 token）。
- 一次只 build 一個映像；build 期間不要同時重建其他容器。

## 兩種做法

- 不同模型的向量不能混用。LanceDB 的表名是依模型推導的：bge-m3/1024 用 `knowledge`，
  gemma 用 `knowledge_embeddinggemma_2_768`。換模型之後，backend 就改讀新表；舊表不會被刪，
  回退時可以直接用。
- **簡易切換**（下一節）：pull、build、改 `.env`、重開。重開後 backend 會自動在新表建索引，
  實測約 3 分鐘（2013 段，A4000）。這段時間回答不會出錯，但可能沒有引用知識庫。
  embedding 還在下載或載入模型時，backend 會每 10 秒重試一次，等它好了再接著建索引，
  不需要手動處理。
- **不停機切換**（「步驟」一節）：先開一個臨時的 gemma 容器，在背景把新表建好再切換，
  重開後約 10 秒就 Ready。步驟比較多。

## 簡易切換

```bash
docker tag "$(docker compose images -q embedding)" jtai-embedding:pre-gemma   # 回退用
git pull
docker compose build embedding          # 只 build 這一個；線上照常
```

`.env` 裡的這兩行改成下面的值（也可以直接刪掉，程式預設就是 gemma）：

```env
EMBEDDING_EXPECTED_MODEL=google/embeddinggemma-2
EMBEDDING_EXPECTED_DIMENSION=768
```

```bash
docker compose up -d --force-recreate embedding backend
docker compose logs -f backend | grep "\[RAG\]"   # 等到 "[RAG] Ready — ... chunks"
```

驗證方式見後面的「驗證」。

## 步驟（不停機切換）

以下指令都在專案根目錄執行。

### 1. 備份目前的 embedding 映像（回退用）

```bash
docker tag "$(docker compose images -q embedding)" jtai-embedding:pre-gemma
```

### 2. 更新程式並 build 新的 embedding 映像

```bash
git pull
docker compose build embedding
```

`docker compose build` 不會動到正在跑的容器，線上服務照常。只 `git pull` 而還沒切換時，
就算 backend 重啟也沒關係：`.env` 還是 bge，程式會沿用舊的 `knowledge` 表，
查詢也會退回 bge 認得的 `query` 語意。

### 3. 開臨時的 gemma embedding 容器，等模型載入

```bash
docker compose run -d --rm --no-deps --name jtai-embedding-prebuild embedding
docker logs -f jtai-embedding-prebuild   # 看到 "Embedding model loaded." 就可以 Ctrl-C
```

第一次會下載模型到 `./.hf_cache`；之後正式的容器會直接沿用，不必再下載。

### 4. 在背景建新索引

```bash
docker compose exec -u appuser \
  -e EMBEDDING_SERVICE_URL=http://jtai-embedding-prebuild:8009 \
  -e EMBEDDING_EXPECTED_MODEL=google/embeddinggemma-2 \
  -e EMBEDDING_EXPECTED_DIMENSION=768 \
  backend python scripts/prebuild_rag_index.py
```

- 預期輸出最後一行是 `chunks: <數量> in knowledge_embeddinggemma_2_768`，而且 exit code 是 0。
- 只要有任何檔案索引失敗，腳本會列出錯誤並以 1 結束。**這時不要切換**，修好之後重跑即可；
  沒變的檔案會依 fingerprint 跳過。
- 這一步用的是線上 backend 容器裡已經 `git pull` 下來的新程式（`./app` 有掛載進容器），
  不會影響線上服務。

### 5. 收掉臨時容器，改 `.env`

```bash
docker stop jtai-embedding-prebuild
```

`.env` 裡的這兩行改成下面的值（也可以直接刪掉，程式預設就是 gemma）：

```env
EMBEDDING_EXPECTED_MODEL=google/embeddinggemma-2
EMBEDDING_EXPECTED_DIMENSION=768
```

`COMPOSE_PROFILES=embedding` 和 `EMBEDDING_SERVICE_URL`（本地模式是 `http://embedding:8009`
或不設）都不用改。

### 6. 切換

```bash
docker compose up -d --force-recreate embedding backend
```

## 驗證

```bash
docker compose logs backend | grep "\[RAG\] Ready"
# 預期：Ready — <與步驟 4 相同的數量> chunks indexed in 約 10s

curl -s http://localhost:<PORT>/health
# 預期："embedding": true
```

接著用前端或 API 分別問 jti、hciot 各一題知識庫裡有的問題，確認回答有引用到正確的段落。

如果 log 出現 `[RAG] Another worker is indexing; waiting for it to finish`：通常是舊容器被砍掉時
還握著 Redis 鎖。鎖只有 60 秒 TTL，持有者活著時才會續約，所以一分鐘內就會自己過期，
worker 接著繼續，不需要手動處理。

## 回退

舊的 `knowledge` 表還在，回退不需要重建索引：

```bash
git checkout <切換前的 commit> -- app docker docker-compose.yml pyproject.toml uv.lock
docker tag jtai-embedding:pre-gemma "$(docker compose config --images | grep embedding)"
# .env 改回 EMBEDDING_EXPECTED_MODEL=BAAI/bge-m3、EMBEDDING_EXPECTED_DIMENSION=1024
docker compose up -d --force-recreate embedding backend
```

## 檢索行為的差異

- 查詢用 `search_query` 語意（前綴 `task: search result | query: `），文件用 `document` 語意，
  並以 topic 標籤作為標題。前綴必須跟 openVman 共用服務完全一致：兩邊算出的向量相同
  （cos = 1.0），本地和共用的服務可以互換。
- `RAG_DISTANCE_THRESHOLD` 維持 0.85。這個值在 bge 和 gemma 下都等於不過濾。
- jtai 自己的 85 題口語改寫題，Recall@5：gemma 80、bge 83。模糊問法略弱，
  一般問法的回答沒有差異。
