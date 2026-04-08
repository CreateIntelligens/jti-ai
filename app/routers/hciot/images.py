"""HCIoT image serving from HCIOT_IMAGES_DIR."""

import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.auth import verify_admin

router = APIRouter(tags=["HCIoT Images"])
admin_router = APIRouter(tags=["HCIoT Admin Images"], dependencies=[Depends(verify_admin)])

_IMAGES_DIR = Path("/app/data/hciot/images")
_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


def _find_image(image_id: str) -> Path | None:
    for ext in _EXTENSIONS:
        candidate = _IMAGES_DIR / f"{image_id}{ext}"
        if candidate.exists():
            return candidate
    return None


@router.get("/images/{image_id}")
def get_image(image_id: str):
    path = _find_image(image_id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    return FileResponse(str(path), media_type=mime)


@admin_router.get("/")
def list_images():
    images = []
    if _IMAGES_DIR.exists():
        for file_path in _IMAGES_DIR.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in _EXTENSIONS:
                images.append({
                    "filename": file_path.name,
                    "size_bytes": file_path.stat().st_size,
                    "image_id": file_path.stem,
                    "url": f"/api/hciot/images/{file_path.stem}"
                })
    return {"images": images}


@admin_router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    image_id: Optional[str] = Form(None)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in _EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(_EXTENSIONS)}")

    # Check size if available immediately
    if file.size and file.size > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Max 10MB allowed.")

    if image_id:
        target_filename = f"{image_id}{ext}"
    else:
        target_filename = file.filename

    # Create dir if not exists
    _IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    target_path = _IMAGES_DIR / target_filename

    # Check for conflict
    if image_id:
        existing = _find_image(image_id)
        if existing and existing.name != target_filename:
            raise HTTPException(status_code=409, detail=f"Image ID {image_id} already exists with a different extension.")
        if existing and existing.name == target_filename:
            raise HTTPException(status_code=409, detail=f"File {target_filename} already exists.")
    else:
        if target_path.exists():
            raise HTTPException(status_code=409, detail=f"File {target_filename} already exists.")

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Max 10MB allowed.")

    with open(target_path, "wb") as f:
        f.write(contents)

    return {
        "filename": target_filename,
        "image_id": target_path.stem,
        "url": f"/api/hciot/images/{target_path.stem}"
    }


@admin_router.delete("/{filename}")
def delete_image(filename: str):
    target_path = _IMAGES_DIR / filename
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"Image {filename} not found.")

    target_path.unlink()
    return {"status": "success", "message": f"Deleted {filename}"}
