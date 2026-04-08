"""HCIoT image serving from MongoDB."""

import mimetypes
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.auth import verify_admin
from app.services.hciot.image_store import get_hciot_image_store

router = APIRouter(tags=["HCIoT Images"])
admin_router = APIRouter(tags=["HCIoT Admin Images"], dependencies=[Depends(verify_admin)])

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")


@router.get("/images/{image_id}")
def get_image(image_id: str):
    store = get_hciot_image_store()
    image = store.get_image(image_id)
    if not image:
        raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")

    mime = image.get("content_type") or "image/jpeg"
    return Response(content=image["data"], media_type=mime)


@admin_router.get("/")
def list_images():
    store = get_hciot_image_store()
    images = store.list_images()
    return {"images": images}


@admin_router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    image_id: str | None = Form(None)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    parsed = PurePosixPath(file.filename)
    ext = parsed.suffix.lower()
    if ext not in _EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(_EXTENSIONS)}")

    if file.size and file.size > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Max 10MB allowed.")

    actual_image_id = image_id or parsed.stem
    store = get_hciot_image_store()

    if store.image_exists(actual_image_id):
        raise HTTPException(status_code=409, detail=f"Image ID {actual_image_id} already exists.")

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Max 10MB allowed.")

    mime = file.content_type or mimetypes.guess_type(file.filename)[0] or "image/jpeg"

    success = store.insert_image(actual_image_id, contents, content_type=mime)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to store image in database.")

    return {
        "filename": file.filename,
        "image_id": actual_image_id,
        "url": f"/api/hciot/images/{actual_image_id}"
    }


@admin_router.delete("/{image_id}")
def delete_image(image_id: str):
    store = get_hciot_image_store()

    # Callers may pass "IMG_001.jpg"; the store key is always the stem
    if "." in image_id:
        image_id = PurePosixPath(image_id).stem

    success = store.delete_image(image_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Image {image_id} not found.")

    return {"status": "success", "message": f"Deleted {image_id}"}
