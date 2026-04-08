## 1. Backend — HciotImageStore

- [ ] 1.1 Create `app/services/hciot/image_store.py`: `HciotImageStore` class with `get_image`, `list_images`, `insert_image`, `delete_image` methods + `get_hciot_image_store` singleton
- [ ] 1.2 Create `tests/hciot/test_image_store.py`: tests for insert/get, duplicate rejection, list (no data field), delete (returns bool), get nonexistent

## 2. Backend — Rewrite Image API

- [ ] 2.1 Rewrite `app/routers/hciot/images.py`: `get_image` reads from MongoDB; `list_images` returns from MongoDB with `url`; `upload_image` stores via `insert_image`; `delete_image` uses `image_id` (not filename)
- [ ] 2.2 Create `tests/hciot/test_image_api.py`: integration tests for upload+serve, upload without image_id uses stem, duplicate 409, list, delete, serve nonexistent

## 3. Migration Script

- [ ] 3.1 Create `scripts/migrate_hciot_images_to_mongo.py`: scan `/app/data/hciot/images/`, insert each file into MongoDB via `image_store.insert_image`, skip already-migrated, print summary; idempotent

## 4. Frontend — Unified image_id

- [ ] 4.1 Create/update `frontend/src/utils/hciotImage.ts`: `normalizeImageId(raw?)` strips extension; `getHciotImageUrl(imageId?)` returns `/api/hciot/images/{encoded_id}` or null
- [ ] 4.2 Update `HciotImage` interface in `frontend/src/services/api/hciot.ts`: remove `filename`, use `image_id` as primary key; update `deleteHciotImage` to use `image_id`
- [ ] 4.3 Update `MergedCsvTable.tsx`: replace inline URL construction with `getHciotImageUrl(row.img)`
- [ ] 4.4 Update `ImageDetailPane.tsx`: use `image_id` instead of `filename` in all display fields
- [ ] 4.5 Update `shared.ts` `buildExplorerTree`: image nodes use `img.image_id` as key and label
- [ ] 4.6 Update `ExplorerSidebar.tsx`: click handler calls `onSelectImage(node.image.image_id)`
- [ ] 4.7 Update `HciotKnowledgeWorkspace.tsx`: `selectedImage` lookup by `image_id`; `handleDeleteImage` calls `api.deleteHciotImage(selectedImage.image_id)`

## 5. Frontend — Image Upload in MergedCsvTable

- [ ] 5.1 Add `onUploadImage?: (file: File) => Promise<{ image_id: string }>` prop to `MergedCsvTable`
- [ ] 5.2 Replace img column text input with upload button + thumbnail preview in editing mode (show remove button when image_id set, upload label when empty)
- [ ] 5.3 Pass `onUploadImage` from `MergedCsvPane` using `uploadHciotImage`
- [ ] 5.4 Add CSS in `workspace.css` for `.hciot-merged-csv-img-cell`, `.hciot-merged-csv-upload-btn`

## 6. Cleanup & Verification

- [ ] 6.1 Grep `app/` for remaining `/app/data/hciot/images` and `_find_image` references — should be zero
- [ ] 6.2 Run full test suite: `docker compose exec backend pytest tests/hciot/ -v`
