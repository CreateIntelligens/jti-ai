## Context

HCIoT Knowledge Workspace 現有圖片儲存架構：
- **儲存位置**：`/app/data/hciot/images/`（container 檔案系統）
- **Serve endpoint**：`GET /api/hciot/images/{image_id}` → 讀 `_find_image(image_id)` 掃描目錄
- **Admin endpoints**：`GET /list`, `POST /upload`, `DELETE /{filename}` 也都操作檔案系統
- **Frontend image_id**：格式不一致，MergedCsvTable 以 inline URL 處理副檔名 strip

知識檔案（文字、CSV、PDF）已統一存 MongoDB（`HciotKnowledgeStore`），圖片是唯一例外。

## Goals / Non-Goals

**Goals:**
- 圖片存入 MongoDB（`hciot_images` collection，`Binary(data)`）
- 所有 API endpoint 改從 MongoDB 讀寫
- 提供一次性遷移腳本
- 統一 `image_id` 格式（不含副檔名）
- MergedCsvTable 編輯模式支援 inline 圖片上傳

**Non-Goals:**
- 圖片壓縮或 CDN 整合
- 多語系圖片（圖片不分語言）
- 圖片版本控制

## Decisions

### 1. 儲存格式：Binary vs GridFS

**選擇：`bson.Binary(data)` 直接嵌入 document**

理由：
- 衛教圖片通常 < 2MB，遠低於 MongoDB 16MB document 限制
- 與 `HciotKnowledgeStore` 做法一致（`data` 欄位也是 `Binary`）
- GridFS 複雜度較高，對此規模不必要

### 2. Collection schema

```
hciot_images: {
  image_id: str,       # 主鍵，無副檔名 (e.g. "IMG_T02_006")
  data: Binary,
  content_type: str,   # e.g. "image/png"
  size: int,           # bytes
  created_at: datetime
}
```

Index: unique on `image_id`

### 3. Delete API 從 filename → image_id

舊版 `DELETE /hciot-admin/images/{filename}` 接受含副檔名的 filename（如 `IMG_001.jpg`）。
**新版改為 `DELETE /hciot-admin/images/{image_id}`**（不含副檔名）。

前端 `handleDeleteImage` 已改用 `selectedImage.image_id`；若有舊 client 傳 filename 含副檔名，server 仍以 `image_id` 查詢 MongoDB，不影響結果。

### 4. 前端 normalizeImageId 工具

CSV 的 `img` 欄位在歷史資料中可能含副檔名（`IMG_001.png`）或路徑（`images/IMG_001.png`）。
統一在 `frontend/src/utils/hciotImage.ts` 做 normalize，所有元件引用此工具，不在各處重複 strip 邏輯。

### 5. 遷移腳本策略

- 遷移前先 `get_image(image_id)` 確認不存在，skip 已遷移的
- 遷移後不刪除檔案系統（安全起見），由 ops 手動確認後再清理
- 腳本設計為冪等（可重複執行）
