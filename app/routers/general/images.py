"""General per-store image serving from MongoDB (store_name-scoped)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.auth import require_kb_access
from app.services.general.image_store import get_general_image_store

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
# Allowlist of MIME types we will serve with their declared type. Anything else
# (e.g. text/html, image/svg+xml) is served as an opaque download to prevent
# stored XSS via a malicious "image" upload.
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
# Defense-in-depth headers: never sniff, never execute, force non-rendering.
_SAFE_IMAGE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
}

router = APIRouter(tags=["General Images"])
admin_router = APIRouter(
    tags=["General Admin Images"], dependencies=[Depends(require_kb_access("general"))]
)


@router.get("/stores/{store_name}/images/{image_id}")
def get_image(store_name: str, image_id: str):
    doc = get_general_image_store().get_image(store_name, image_id)
    if not doc:
        raise HTTPException(status_code=404, detail="image not found")
    declared = doc.get("content_type") or "image/png"
    # Don't trust the stored content_type: only serve allowlisted image types
    # with their declared MIME; serve anything else as an opaque download.
    media_type = declared if declared in ALLOWED_IMAGE_TYPES else "application/octet-stream"
    headers = dict(_SAFE_IMAGE_HEADERS)
    if media_type == "application/octet-stream":
        headers["Content-Disposition"] = "attachment"
    return Response(content=doc["data"], media_type=media_type, headers=headers)


@admin_router.get("/stores/{store_name}/images")
def list_images(store_name: str):
    return {"images": get_general_image_store().list_images(store_name)}


@admin_router.post("/stores/{store_name}/images", status_code=status.HTTP_201_CREATED)
async def upload_image(store_name: str, image_id: str = Form(...), file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="image too large")
    get_general_image_store().upsert_image(
        store_name, image_id, data, file.content_type or "image/png"
    )
    return {"image_id": image_id, "url": f"/api/general/stores/{store_name}/images/{image_id}"}


@admin_router.delete("/stores/{store_name}/images/{image_id}")
def delete_image(store_name: str, image_id: str):
    if not get_general_image_store().delete_image(store_name, image_id):
        raise HTTPException(status_code=404, detail="image not found")
    return {"ok": True}
