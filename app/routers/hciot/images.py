"""HCIoT image serving from HCIOT_IMAGES_DIR."""

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

_IMAGES_DIR = Path("/app/data/hciot/images")
_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")


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
