## Context

HCIoT Knowledge Workspace 是醫院衛教知識管理介面，目前有：
- **ExplorerSidebar**：樹狀結構瀏覽 category > topic > files
- **FileDetailPane**：選中檔案後顯示 metadata 編輯 + 內容預覽/編輯
- **UploadDialog**：上傳檔案 or 手動輸入 Q&A（兩個 tab）
- **images.py**：靜態圖片 serve（`GET /hciot/images/{image_id}`），無上傳功能

知識檔案存 MongoDB（`knowledge_store`），圖片存檔案系統（`data/hciot/images/`）。CSV 格式為 `index,q,a,img`，每個 topic 可能有一個主 CSV + 多個 IMG CSV（單題帶圖拆出的檔案）。

## Goals / Non-Goals

**Goals:**
- 上傳 UX 提升：進度狀態、類型 icon、重複檔名提示
- CSV 整合預覽：同 topic 下多個 CSV 合併為一個 Q&A 表格，作為 FileDetailPane 預設 tab
- 圖片管理：讓非技術人員能透過 UI 上傳/查看/刪除衛教圖片

**Non-Goals:**
- 圖片裁剪/壓縮等編輯功能
- CSV 表格內直接編輯（仍用原始文字編輯）
- 圖片存 MongoDB（決定用檔案系統）
- 批次圖片自動命名規則（使用者自行填寫 IMG ID）

## Decisions

### 1. CSV 整合：後端 API vs 前端合併

**選擇：新增後端 API `GET /hciot-admin/knowledge/topic-csv-merged?topic_id=X&language=Y`**

理由：
- 前端只有檔案列表（不含 data），要合併得先逐一下載每個 CSV 的 content，多次 API call
- 後端可直接從 MongoDB 讀取同 topic 所有 CSV 的 data bytes，一次合併回傳
- 回傳格式：`{ rows: [{index, q, a, img}], source_files: [filename1, filename2] }`

替代方案（前端合併）：需要 N 次 `GET /files/{filename}/content` call，UX 較差。

### 2. 圖片存儲：檔案系統

**選擇：繼續用 `data/hciot/images/` 檔案系統**

理由：
- docker-compose 已有 `./data:/app/data` volume mount
- 現有 `images.py` 的 `GET /hciot/images/{image_id}` 直接可用
- 圖片被 chat 回覆引用時用 IMG ID，靜態 serve 效能好
- 只需在 `images.py` 加上傳/列表/刪除 endpoint

### 3. 圖片上傳 API 設計

新增到 `app/routers/hciot/images.py`：
- `GET /hciot-admin/images/` — 列出所有圖片（filename, size, url）
- `POST /hciot-admin/images/upload` — 上傳圖片，form field: `file` + 可選 `image_id`
  - 若有 `image_id`：存為 `{image_id}.{ext}`
  - 若無 `image_id`：用原始檔名
  - 檔名衝突時回 409
- `DELETE /hciot-admin/images/{filename}` — 刪除圖片檔案

### 4. FileDetailPane tab 架構

在 FileDetailPane 頂部加 tab bar：
- **「整合預覽」**（預設）：當選中的檔案屬於某 topic 時，顯示該 topic 所有 CSV 合併的表格；若 topic 無 CSV 則顯示 fallback
- **「檔案內容」**：原本的單檔預覽/編輯功能

若檔案沒有 topic_id，只顯示「檔案內容」tab（無整合可顯示）。

### 5. 圖片在 Explorer 的呈現

在 ExplorerSidebar 樹的最底部加一個「圖片」頂層節點（與 category 同級），展開後列出所有圖片檔案。點擊圖片時右側顯示圖片預覽 + metadata。

### 6. UploadDialog 優化項目

- 每個檔案顯示上傳狀態 icon（pending / uploading / done / error）
- 根據副檔名顯示類型 icon（CSV, PDF, Word, TXT, 圖片）
- 選檔時檢查是否有同名檔案已在 selectedFiles 列表中，提示使用者

## Risks / Trade-offs

- **[圖片檔名衝突]** → API 回 409，前端提示使用者改名
- **[大圖片上傳]** → 前端限制 10MB，後端也做 size check
- **[CSV 合併效能]** → 同 topic 通常不超過 20 個 CSV，後端合併足夠快
- **[圖片目錄權限]** → container 內 `data/hciot/images/` 需要寫入權限，現有 volume mount 應該已滿足
