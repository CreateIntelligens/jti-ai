## Why

HCIoT Knowledge Workspace 的上傳體驗需要改善（缺少進度顯示、檔案類型辨識），CSV 知識檔案分散在多個檔案中但檢視時無法整合預覽，且衛教圖片目前只能手動放入伺服器檔案系統，沒有 UI 讓非技術人員上傳管理。

## What Changes

- **上傳頁面優化**：UploadDialog 加入每檔上傳狀態指示、檔案類型 icon、重複檔名提示
- **CSV 整合檢視**：FileDetailPane 預設顯示同 topic 下所有 CSV 合併的 Q&A 表格，可切換 tab 看單檔原始內容
- **圖片管理目錄**：Knowledge Workspace Explorer 新增「圖片」區域，支援上傳圖片到 `data/hciot/images/`，上傳時可選填圖片檔名（IMG ID），批次上傳時自動編號，單張上傳讓使用者自己填

## Capabilities

### New Capabilities
- `csv-merged-view`: Topic 級別 CSV 整合表格預覽，合併主 CSV 和 IMG CSV 為統一 Q&A 表格
- `image-management`: 圖片上傳、列表、刪除 API 及前端 UI，存儲在檔案系統 `data/hciot/images/`

### Modified Capabilities
- `upload-dialog`: 改善上傳 UX — 進度指示、檔案類型 icon、重複檔名檢查

## Impact

- **Frontend**: `UploadDialog.tsx`, `FileDetailPane.tsx`, `ExplorerSidebar.tsx`, `HciotKnowledgeWorkspace.tsx`, `workspace.css`
- **Backend**: `app/routers/hciot/images.py`（新增上傳/列表/刪除 API）, `app/routers/hciot/knowledge.py`（新增 topic CSV 合併 API）
- **API**: 新增 `POST /hciot-admin/images/upload`, `GET /hciot-admin/images/`, `DELETE /hciot-admin/images/{image_id}`, `GET /hciot-admin/knowledge/topic/{topic_id}/merged-csv`
