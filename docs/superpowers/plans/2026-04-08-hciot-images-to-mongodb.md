# HCIoT Images: Filesystem → MongoDB Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate HCIoT image storage from container filesystem (`/app/data/hciot/images/`) to MongoDB Binary, matching the existing knowledge_store pattern. Unify image_id format (no file extensions) and add image upload support to the MergedCsvTable editing view.

**Architecture:** New `HciotImageStore` class stores images in a `hciot_images` MongoDB collection using `Binary(data)`. The existing `GET /api/hciot/images/{image_id}` serve endpoint reads from DB instead of disk. Admin endpoints (list/upload/delete) are rewritten to use the store. The frontend MergedCsvTable gets an upload button in the img column during editing mode.

**Tech Stack:** FastAPI, MongoDB (pymongo, bson.Binary), React, TypeScript

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/services/hciot/image_store.py` | MongoDB image store (CRUD, singleton) |
| Rewrite | `app/routers/hciot/images.py` | All image endpoints use image_store instead of filesystem |
| Modify | `frontend/src/components/hciot/knowledgeWorkspace/MergedCsvTable.tsx` | Add image upload button in editing mode |
| Modify | `frontend/src/services/api/hciot.ts` | Ensure `uploadHciotImage` returns `image_id` consistently |
| Modify | `frontend/src/utils/hciotImage.ts` | Strip file extension from image_id if present |
| Create | `tests/hciot/test_image_store.py` | Unit tests for image store |
| Create | `tests/hciot/test_image_api.py` | Integration tests for image API endpoints |

---

### Task 1: Create `HciotImageStore`

**Files:**
- Create: `app/services/hciot/image_store.py`
- Create: `tests/hciot/test_image_store.py`

- [ ] **Step 1: Write failing tests for image store**

```python
# tests/hciot/test_image_store.py
"""Tests for HciotImageStore MongoDB operations."""
import pytest
from app.services.hciot.image_store import HciotImageStore

SAMPLE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal fake PNG bytes


@pytest.fixture
def store():
    s = HciotImageStore()
    # Clean up before each test
    s.collection.delete_many({})
    yield s
    s.collection.delete_many({})


def test_insert_and_get(store):
    meta = store.insert_image("test_001", SAMPLE_PNG, "image/png")
    assert meta["image_id"] == "test_001"
    assert meta["content_type"] == "image/png"
    assert meta["size"] == len(SAMPLE_PNG)

    doc = store.get_image("test_001")
    assert doc is not None
    assert doc["data"] == SAMPLE_PNG


def test_insert_duplicate_raises(store):
    store.insert_image("dup_001", SAMPLE_PNG, "image/png")
    with pytest.raises(ValueError, match="already exists"):
        store.insert_image("dup_001", SAMPLE_PNG, "image/png")


def test_list_images(store):
    store.insert_image("img_a", SAMPLE_PNG, "image/png")
    store.insert_image("img_b", SAMPLE_PNG, "image/jpeg")
    result = store.list_images()
    assert len(result) == 2
    ids = {r["image_id"] for r in result}
    assert ids == {"img_a", "img_b"}
    # Should not include binary data in list
    for r in result:
        assert "data" not in r


def test_delete_image(store):
    store.insert_image("del_001", SAMPLE_PNG, "image/png")
    assert store.delete_image("del_001") is True
    assert store.get_image("del_001") is None
    assert store.delete_image("del_001") is False


def test_get_nonexistent(store):
    assert store.get_image("nope") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/hciot/test_image_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.hciot.image_store'`

- [ ] **Step 3: Implement `HciotImageStore`**

```python
# app/services/hciot/image_store.py
"""MongoDB-backed HCIoT image storage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson.binary import Binary

from app.services.mongo_client import get_mongo_db


class HciotImageStore:
    COLLECTION = "hciot_images"

    def __init__(self):
        self.db = get_mongo_db()
        self.collection = self.db[self.COLLECTION]

    def get_image(self, image_id: str) -> dict[str, Any] | None:
        doc = self.collection.find_one({"image_id": image_id})
        if not doc:
            return None
        doc.pop("_id", None)
        data = doc.get("data")
        if isinstance(data, Binary):
            doc["data"] = bytes(data)
        return doc

    def list_images(self) -> list[dict[str, Any]]:
        cursor = self.collection.find(
            {},
            {"_id": 0, "image_id": 1, "content_type": 1, "size": 1, "created_at": 1},
        ).sort("image_id", 1)
        return list(cursor)

    def insert_image(
        self,
        image_id: str,
        data: bytes,
        content_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        if self.collection.find_one({"image_id": image_id}, {"_id": 1}):
            raise ValueError(f"Image '{image_id}' already exists")

        now = datetime.now(timezone.utc)
        doc = {
            "image_id": image_id,
            "data": Binary(data),
            "content_type": content_type,
            "size": len(data),
            "created_at": now,
        }
        self.collection.insert_one(doc)
        return {
            "image_id": image_id,
            "content_type": content_type,
            "size": len(data),
            "created_at": now,
        }

    def delete_image(self, image_id: str) -> bool:
        return self.collection.delete_one({"image_id": image_id}).deleted_count > 0


_image_store: HciotImageStore | None = None


def get_hciot_image_store() -> HciotImageStore:
    global _image_store
    if _image_store is None:
        _image_store = HciotImageStore()
    return _image_store
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/hciot/test_image_store.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/hciot/image_store.py tests/hciot/test_image_store.py
git commit -m "feat(hciot): add MongoDB-backed image store"
```

---

### Task 2: Rewrite image API endpoints to use MongoDB

**Files:**
- Rewrite: `app/routers/hciot/images.py`
- Create: `tests/hciot/test_image_api.py`

- [ ] **Step 1: Write failing API tests**

```python
# tests/hciot/test_image_api.py
"""Integration tests for HCIoT image API endpoints."""
import io
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.hciot.image_store import get_hciot_image_store

SAMPLE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


@pytest.fixture(autouse=True)
def clean_images():
    store = get_hciot_image_store()
    store.collection.delete_many({})
    yield
    store.collection.delete_many({})


@pytest.fixture
def client():
    return TestClient(app)


def _upload(client, filename="test.png", image_id=None, data=SAMPLE_PNG):
    files = {"file": (filename, io.BytesIO(data), "image/png")}
    form = {}
    if image_id:
        form["image_id"] = image_id
    return client.post("/api/hciot-admin/images/upload", files=files, data=form)


def test_upload_and_serve(client):
    resp = _upload(client, image_id="TEST_001")
    assert resp.status_code == 201
    body = resp.json()
    assert body["image_id"] == "TEST_001"

    # Serve via public endpoint
    serve = client.get("/api/hciot/images/TEST_001")
    assert serve.status_code == 200
    assert serve.headers["content-type"].startswith("image/")


def test_upload_without_image_id_uses_stem(client):
    resp = _upload(client, filename="my_photo.png")
    assert resp.status_code == 201
    assert resp.json()["image_id"] == "my_photo"


def test_upload_duplicate_rejects(client):
    _upload(client, image_id="DUP")
    resp = _upload(client, image_id="DUP")
    assert resp.status_code == 409


def test_list_images(client):
    _upload(client, image_id="A")
    _upload(client, image_id="B")
    resp = client.get("/api/hciot-admin/images/")
    assert resp.status_code == 200
    ids = {img["image_id"] for img in resp.json()["images"]}
    assert ids == {"A", "B"}


def test_delete_image(client):
    _upload(client, image_id="DEL")
    resp = client.delete("/api/hciot-admin/images/DEL")
    assert resp.status_code == 200

    serve = client.get("/api/hciot/images/DEL")
    assert serve.status_code == 404


def test_serve_nonexistent(client):
    resp = client.get("/api/hciot/images/NOPE")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to see current state**

Run: `docker compose exec backend pytest tests/hciot/test_image_api.py -v`
Expected: Some tests may pass against old filesystem impl, but behavior will diverge.

- [ ] **Step 3: Rewrite `app/routers/hciot/images.py`**

```python
# app/routers/hciot/images.py
"""HCIoT image API — serves and manages images stored in MongoDB."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.auth import verify_admin
from app.services.hciot.image_store import get_hciot_image_store

router = APIRouter(tags=["HCIoT Images"])
admin_router = APIRouter(tags=["HCIoT Admin Images"], dependencies=[Depends(verify_admin)])

_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB


# ── Public: serve image ──────────────────────────────────────

@router.get("/images/{image_id}")
def get_image(image_id: str):
    store = get_hciot_image_store()
    doc = store.get_image(image_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")
    return Response(
        content=doc["data"],
        media_type=doc.get("content_type", "image/jpeg"),
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ── Admin: list / upload / delete ────────────────────────────

@admin_router.get("/")
def list_images():
    store = get_hciot_image_store()
    images = store.list_images()
    for img in images:
        img["url"] = f"/api/hciot/images/{img['image_id']}"
    return {"images": images}


@admin_router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    image_id: str | None = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in _EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(_EXTENSIONS))}",
        )

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Max 10 MB.")

    resolved_id = image_id.strip() if image_id else Path(file.filename).stem
    content_type = file.content_type or "image/jpeg"

    store = get_hciot_image_store()
    try:
        meta = store.insert_image(resolved_id, contents, content_type)
    except ValueError:
        raise HTTPException(status_code=409, detail=f"Image ID '{resolved_id}' already exists.")

    return {
        "image_id": meta["image_id"],
        "size": meta["size"],
        "url": f"/api/hciot/images/{meta['image_id']}",
    }


@admin_router.delete("/{image_id}")
def delete_image(image_id: str):
    store = get_hciot_image_store()
    if not store.delete_image(image_id):
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found.")
    return {"status": "success", "message": f"Deleted {image_id}"}
```

Key changes from the old version:
- `get_image` reads from MongoDB instead of filesystem `_find_image`
- `upload_image` stores `Binary(contents)` in MongoDB via `image_store.insert_image`
- `delete_image` takes `image_id` (not filename with extension)
- `list_images` returns from MongoDB, no filesystem scan
- Removed all `Path("/app/data/hciot/images")` references

- [ ] **Step 4: Run API tests**

Run: `docker compose exec backend pytest tests/hciot/test_image_api.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/hciot/images.py tests/hciot/test_image_api.py
git commit -m "feat(hciot): migrate image API from filesystem to MongoDB"
```

---

### Task 3: Migrate existing filesystem images to MongoDB

**Files:**
- Create: `scripts/migrate_hciot_images_to_mongo.py`

- [ ] **Step 1: Write migration script**

```python
# scripts/migrate_hciot_images_to_mongo.py
"""One-time migration: move HCIoT images from /app/data/hciot/images/ to MongoDB."""

import mimetypes
from pathlib import Path

from app.services.hciot.image_store import get_hciot_image_store

IMAGES_DIR = Path("/app/data/hciot/images")
EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def migrate():
    if not IMAGES_DIR.exists():
        print("No images directory found, nothing to migrate.")
        return

    store = get_hciot_image_store()
    migrated = 0
    skipped = 0

    for path in sorted(IMAGES_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue

        image_id = path.stem
        if store.get_image(image_id):
            print(f"  SKIP (exists): {image_id}")
            skipped += 1
            continue

        data = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "image/jpeg"
        store.insert_image(image_id, data, content_type)
        print(f"  OK: {image_id} ({len(data)} bytes)")
        migrated += 1

    print(f"\nDone. Migrated: {migrated}, Skipped: {skipped}")


if __name__ == "__main__":
    migrate()
```

- [ ] **Step 2: Run migration inside container**

Run: `docker compose exec backend python -m scripts.migrate_hciot_images_to_mongo`
Expected: Prints each migrated image_id, final summary.

- [ ] **Step 3: Verify images serve correctly from MongoDB**

Run: `docker compose exec backend python -c "from app.services.hciot.image_store import get_hciot_image_store; store = get_hciot_image_store(); imgs = store.list_images(); print(f'{len(imgs)} images in MongoDB'); [print(f'  {i[\"image_id\"]}') for i in imgs]"`
Expected: All previously-filesystem images now listed.

- [ ] **Step 4: Commit**

```bash
git add scripts/migrate_hciot_images_to_mongo.py
git commit -m "chore(hciot): add one-time image migration script (filesystem → MongoDB)"
```

---

### Task 4: Update frontend — consistent image_id format

**Files:**
- Modify: `frontend/src/utils/hciotImage.ts`
- Modify: `frontend/src/services/api/hciot.ts`
- Modify: `frontend/src/components/hciot/knowledgeWorkspace/MergedCsvTable.tsx`
- Modify: `frontend/src/components/hciot/knowledgeWorkspace/ImageDetailPane.tsx`

- [ ] **Step 1: Normalize image_id in `hciotImage.ts` — strip extension**

```typescript
// frontend/src/utils/hciotImage.ts
export function normalizeImageId(raw?: string): string {
  const trimmed = raw?.trim() ?? '';
  // Strip file extension if present (e.g. "IMG_001.png" → "IMG_001")
  return trimmed.replace(/\.[^.]+$/, '');
}

export function getHciotImageUrl(imageId?: string): string | null {
  const normalized = normalizeImageId(imageId);
  if (!normalized) return null;
  return `/api/hciot/images/${encodeURIComponent(normalized)}`;
}
```

- [ ] **Step 2: Update `HciotImage` interface — remove `filename`, use `image_id` as primary**

In `frontend/src/services/api/hciot.ts`, update the interface:

```typescript
export interface HciotImage {
  image_id: string;
  size?: number;
  url: string;
  content_type?: string;
}
```

Update `listHciotImages`:

```typescript
export async function listHciotImages(): Promise<{ images: HciotImage[] }> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/images/`);
  return handleResponse<{ images: HciotImage[] }>(response);
}
```

Update `deleteHciotImage` to use `image_id`:

```typescript
export async function deleteHciotImage(imageId: string): Promise<void> {
  const response = await fetchAsAdmin(`${HCIOT_ADMIN_BASE}/images/${encodeURIComponent(imageId)}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}
```

`uploadHciotImage` stays the same — already returns `image_id`.

- [ ] **Step 3: Update `MergedCsvTable.tsx` — use `getHciotImageUrl` instead of inline URL**

Replace the inline URL construction:

```tsx
import { getHciotImageUrl } from '../../../utils/hciotImage';

// In the img cell (non-editing mode), replace:
//   src={`/api/hciot/images/${row.img.replace(/\.[^.]+$/, '')}`}
// with:
//   src={getHciotImageUrl(row.img) ?? ''}
```

- [ ] **Step 4: Update `ImageDetailPane.tsx` — use `image_id` instead of `filename`**

Update references from `selectedImage.filename` to `selectedImage.image_id`:

```tsx
<h2 className="hciot-file-title">{selectedImage.image_id}</h2>
// ...
<span>ID: {selectedImage.image_id}</span>
<span>{selectedImage.size ? `${Math.max(1, Math.round(selectedImage.size / 1024))} KB` : '0 KB'}</span>
```

- [ ] **Step 5: Update `ExplorerSidebar` and `shared.ts` — image node uses `image_id`**

In `shared.ts` `buildExplorerTree`, the image node currently uses `img.filename`. Update to `img.image_id`:

```typescript
// In buildExplorerTree, image nodes section:
.map((img) => ({
  key: `image:${img.image_id}`,
  kind: 'image',
  label: img.image_id,
  image: img,
}));
```

Update `ExplorerSidebar` click handler — `onSelectImage(node.image.image_id)`.

Update `HciotKnowledgeWorkspace` — `selectedImage` lookup uses `image_id`:

```typescript
const selectedImage = useMemo(
  () => images.find((img) => img.image_id === selectedImageName) || null,
  [images, selectedImageName],
);
```

And `handleDeleteImage` uses `api.deleteHciotImage(selectedImage.image_id)`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/utils/hciotImage.ts \
  frontend/src/services/api/hciot.ts \
  frontend/src/components/hciot/knowledgeWorkspace/MergedCsvTable.tsx \
  frontend/src/components/hciot/knowledgeWorkspace/ImageDetailPane.tsx \
  frontend/src/components/hciot/knowledgeWorkspace/ExplorerSidebar.tsx \
  frontend/src/components/hciot/knowledgeWorkspace/shared.ts \
  frontend/src/components/hciot/HciotKnowledgeWorkspace.tsx
git commit -m "refactor(hciot): unify frontend image references to use image_id"
```

---

### Task 5: Add image upload button in MergedCsvTable editing mode

**Files:**
- Modify: `frontend/src/components/hciot/knowledgeWorkspace/MergedCsvTable.tsx`
- Modify: `frontend/src/components/hciot/knowledgeWorkspace/MergedCsvPane.tsx`

- [ ] **Step 1: Add `onUploadImage` callback to MergedCsvTable props**

```typescript
// In MergedCsvTable.tsx, add to props interface:
interface MergedCsvTableProps {
  // ... existing props ...
  onUploadImage?: (file: File) => Promise<{ image_id: string }>;
}
```

- [ ] **Step 2: Replace text input with upload button + preview in editing mode**

In `MergedCsvTable.tsx`, replace the img column editing cell:

```tsx
<td>
  {isEditing ? (
    <div className="hciot-merged-csv-img-cell">
      {row.img ? (
        <div className="hciot-merged-csv-img-wrapper">
          <img
            src={getHciotImageUrl(row.img) ?? ''}
            alt={row.img}
            className="hciot-merged-csv-thumbnail"
          />
          <button
            type="button"
            className="hciot-explorer-icon-button danger"
            onClick={() => onUpdateRow(i, { img: '' })}
            title={language === 'zh' ? '移除圖片' : 'Remove image'}
          >
            <X size={12} />
          </button>
        </div>
      ) : onUploadImage ? (
        <label className="hciot-merged-csv-upload-btn">
          <ImageIcon size={14} />
          <span>{language === 'zh' ? '上傳' : 'Upload'}</span>
          <input
            type="file"
            accept="image/*"
            hidden
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file || !onUploadImage) return;
              try {
                const res = await onUploadImage(file);
                onUpdateRow(i, { img: res.image_id });
              } catch (err) {
                console.error('Image upload failed:', err);
              }
              e.target.value = '';
            }}
          />
        </label>
      ) : (
        <input
          className="hciot-file-input"
          value={row.img || ''}
          placeholder="image_id"
          onChange={(e) => onUpdateRow(i, { img: e.target.value })}
        />
      )}
    </div>
  ) : row.img ? (
    <div className="hciot-merged-csv-img-wrapper">
      <img
        src={getHciotImageUrl(row.img) ?? ''}
        alt={row.img}
        className="hciot-merged-csv-thumbnail"
        title={row.img}
        onError={(e) => {
          (e.target as HTMLImageElement).style.display = 'none';
          const next = (e.target as HTMLImageElement).nextElementSibling;
          if (next) next.classList.remove('hidden');
        }}
      />
      <span className="hciot-merged-csv-img-text hidden">{row.img}</span>
    </div>
  ) : null}
</td>
```

- [ ] **Step 3: Pass `onUploadImage` from MergedCsvPane**

In `MergedCsvPane.tsx`:

```tsx
import { uploadHciotImage } from '../../../services/api/hciot';

// In the MergedCsvTable usage:
<MergedCsvTable
  // ... existing props ...
  onUploadImage={isEditing ? async (file) => {
    const res = await uploadHciotImage(file);
    return { image_id: res.image_id };
  } : undefined}
/>
```

- [ ] **Step 4: Add minimal CSS for upload button**

In `frontend/src/styles/hciot/workspace.css`, add:

```css
.hciot-merged-csv-img-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.hciot-merged-csv-upload-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: 1px dashed var(--border-color, #d1d5db);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary, #6b7280);
  transition: border-color 0.15s, color 0.15s;
}

.hciot-merged-csv-upload-btn:hover {
  border-color: var(--primary, #3b82f6);
  color: var(--primary, #3b82f6);
}
```

- [ ] **Step 5: Rebuild and verify**

Run: `docker compose up -d --force-recreate backend frontend`
Manual test: Open MergedCsvTable in edit mode → click Upload on an img cell → select image → verify image_id populates and thumbnail shows.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/hciot/knowledgeWorkspace/MergedCsvTable.tsx \
  frontend/src/components/hciot/knowledgeWorkspace/MergedCsvPane.tsx \
  frontend/src/styles/hciot/workspace.css
git commit -m "feat(hciot): add image upload button in merged CSV editing mode"
```

---

### Task 6: Cleanup — remove old filesystem code and data

**Files:**
- Verify: no remaining references to `/app/data/hciot/images`

- [ ] **Step 1: Grep for any remaining filesystem image references**

Run: `grep -r "hciot/images" app/ --include="*.py" | grep -v __pycache__`
Run: `grep -r "IMAGES_DIR\|_find_image" app/ --include="*.py" | grep -v __pycache__`

Expected: Zero matches (all removed in Task 2).

- [ ] **Step 2: Verify migration script ran and images serve from MongoDB**

Run: `docker compose exec backend python -c "from app.services.hciot.image_store import get_hciot_image_store; store = get_hciot_image_store(); print(len(store.list_images()), 'images in DB')"`

- [ ] **Step 3: Commit any cleanup if needed, then final verification**

Run full test suite: `docker compose exec backend pytest tests/hciot/ -v`
Expected: All tests PASS.

```bash
git commit -m "chore(hciot): cleanup filesystem image references" --allow-empty
```
