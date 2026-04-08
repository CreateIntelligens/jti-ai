## Why

HCIoT 圖片目前存在 container 檔案系統（`/app/data/hciot/images/`），這導致容器重建後圖片消失、無法在多副本部署中共享，且 image_id 格式不一致（有些含副檔名、有些不含）。MongoDB 已是知識檔案的儲存後端，圖片應統一存入，方便備份與管理。

## What Changes

- **MongoDB 圖片儲存**：新增 `HciotImageStore`，使用 `hciot_images` collection 存 `Binary(data)`，CRUD 介面與 `HciotKnowledgeStore` 一致
- **Image API 改寫**：所有圖片 endpoint（serve / list / upload / delete）改從 MongoDB 讀寫，移除檔案系統依賴
- **一次性遷移腳本**：將現有 `/app/data/hciot/images/` 內的圖片逐一寫入 MongoDB
- **前端統一 image_id 格式**：`image_id` 永遠不含副檔名，所有元件改用 `normalizeImageId()` 工具函式
- **MergedCsvTable 圖片上傳**：編輯模式下 img 欄位加上「上傳」按鈕，可直接上傳圖片並自動填入 image_id

## Capabilities

### New Capabilities
- `image-store`: MongoDB-backed CRUD for HCIoT images (`HciotImageStore` + `get_hciot_image_store`)
- `image-upload-in-table`: Inline image upload button in MergedCsvTable editing mode

### Modified Capabilities
- `image-management`: Image API endpoints rewritten to use MongoDB instead of filesystem; `image_id` is now the primary key (no extension); delete endpoint uses `image_id` instead of filename

## Impact

- **Backend**: `app/services/hciot/image_store.py`（新建）, `app/routers/hciot/images.py`（改寫）, `scripts/migrate_hciot_images_to_mongo.py`（新建）
- **Frontend**: `frontend/src/utils/hciotImage.ts`, `frontend/src/services/api/hciot.ts`, `frontend/src/components/hciot/knowledgeWorkspace/MergedCsvTable.tsx`, `MergedCsvPane.tsx`, `ImageDetailPane.tsx`, `ExplorerSidebar.tsx`, `shared.ts`, `HciotKnowledgeWorkspace.tsx`
- **Tests**: `tests/hciot/test_image_store.py`（新建）, `tests/hciot/test_image_api.py`（新建）
