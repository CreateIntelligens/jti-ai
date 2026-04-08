## 1. Backend — Image Management API

- [x] 1.1 Extend `app/routers/hciot/images.py`: add `GET /hciot-admin/images/` list endpoint (scan directory, return filename/size/image_id/url)
- [x] 1.2 Add `POST /hciot-admin/images/upload` endpoint (multipart file + optional image_id, 10MB limit, image extension validation, 409 on conflict)
- [x] 1.3 Add `DELETE /hciot-admin/images/{filename}` endpoint (remove file, 404 if missing)
- [x] 1.4 Register new image admin routes in `app/routers/hciot/__init__.py`

## 2. Backend — Merged CSV API

- [x] 2.1 Add `GET /hciot-admin/knowledge/topic-csv-merged` endpoint in `app/routers/hciot/knowledge.py` (query by topic_id + language, read all CSV files from MongoDB, parse and merge rows, return `{rows, source_files}`)
- [x] 2.2 Add CSV merge utility function in `app/services/hciot/csv_utils.py` (parse multiple CSV bytes into unified `[{index, q, a, img}]` list, sort by index)

## 3. Frontend — API Client

- [x] 3.1 Add image API functions in `frontend/src/services/api/hciot.ts`: `listHciotImages()`, `uploadHciotImage(file, imageId?)`, `deleteHciotImage(filename)`
- [x] 3.2 Add merged CSV API function: `getHciotTopicMergedCsv(topicId, language)`

## 4. Frontend — UploadDialog Improvements

- [x] 4.1 Add file type icons based on extension (CSV=Table, PDF=FileText, Word=FileType, Image=ImageIcon, other=File)
- [x] 4.2 Add per-file upload status tracking (pending/uploading/done/error) with status icons
- [x] 4.3 Add duplicate filename detection with warning badge

## 5. Frontend — FileDetailPane Merged View Tab

- [x] 5.1 Add tab bar component to FileDetailPane (「整合預覽」default + 「檔案內容」)
- [x] 5.2 Create MergedCsvTable component (fetch merged data, render table with index/q/a/img columns)
- [x] 5.3 Add image thumbnail in img column (load from `/hciot/images/{image_id}`, fallback to text)
- [x] 5.4 Handle no-topic-id case: hide merged tab, show only file content tab

## 6. Frontend — Image Management UI

- [x] 6.1 Add images data fetching to HciotKnowledgeWorkspace (list images on load, store in state)
- [x] 6.2 Add "圖片" top-level folder node in ExplorerSidebar (show image files, image icon)
- [x] 6.3 Create ImageDetailPane (preview image, show filename/size metadata, delete button)
- [x] 6.4 Create ImageUploadDialog (drag-drop zone, optional image_id text field per file, batch upload support)

## 7. Styling

- [x] 7.1 Add CSS for FileDetailPane tab bar and merged table in `workspace.css`
- [x] 7.2 Add CSS for ImageDetailPane and ImageUploadDialog
- [x] 7.3 Add CSS for upload status icons and file type icons in UploadDialog

## 8. Testing

- [x] 8.1 Backend tests: image list/upload/delete API endpoints
- [x] 8.2 Backend tests: merged CSV API (multiple CSVs, empty topic, no CSV files)
- [x] 8.3 Frontend tests: MergedCsvTable rendering
- [x] 8.4 Frontend tests: UploadDialog status indicators and duplicate detection
