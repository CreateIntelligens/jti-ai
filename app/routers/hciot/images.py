"""HCIoT image serving from MongoDB."""

import mimetypes
import re
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.auth import verify_admin
from app.services.hciot.csv_utils import _parse_csv_rows
from app.services.hciot.image_store import get_hciot_image_store
from app.services.hciot.knowledge_store import get_hciot_knowledge_store

router = APIRouter(tags=["HCIoT Images"])
admin_router = APIRouter(tags=["HCIoT Admin Images"], dependencies=[Depends(verify_admin)])

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
_KNOWLEDGE_LANGUAGES = ("zh", "en")


def _canonicalize_image_id(image_id: str) -> str:
    """Single source of truth for image_id normalization, shared by GET-image
    lookup and reference counting so the two stay in sync."""
    return PurePosixPath(image_id).stem.replace(" ", "")


def _candidate_image_ids(image_id: str) -> list[str]:
    normalized = PurePosixPath(image_id).stem
    canonical = _canonicalize_image_id(image_id)
    # also try inserting a space before opening parenthesis: PRP(1) -> PRP (1)
    spaced = re.sub(r"(\S)\(", r"\1 (", canonical)

    seen: set[str] = set()
    candidate_ids: list[str] = []

    for candidate in [normalized, canonical, spaced]:
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidate_ids.append(candidate)

        stripped = candidate[4:] if candidate.upper().startswith("IMG_") and len(candidate) > 4 else None
        if stripped and stripped not in seen:
            seen.add(stripped)
            candidate_ids.append(stripped)

    return candidate_ids


def _normalize_csv_image_reference(raw: str) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    if "=" in value:
        value = value.split("=", 1)[-1].strip()
    value = PurePosixPath(value).name
    normalized = PurePosixPath(value).stem.strip()
    return normalized or None


def _build_image_reference_counts(image_ids: set[str]) -> dict[str, int]:
    if not image_ids:
        return {}

    counts = {image_id: 0 for image_id in image_ids}
    # canonicalized lookup so "PRP(1)" in CSV can match "PRP (1)" stored in DB
    canonical_to_id: dict[str, str] = {}
    for image_id in image_ids:
        canonical_to_id.setdefault(_canonicalize_image_id(image_id), image_id)

    store = get_hciot_knowledge_store()

    for language in _KNOWLEDGE_LANGUAGES:
        for _filename, data in store.iter_csv_files_with_data(language):
            if not data:
                continue
            parsed = _parse_csv_rows(data)
            if not parsed:
                continue
            fieldnames, parsed_rows = parsed
            if "img" not in fieldnames:
                continue

            for row in parsed_rows:
                reference = _normalize_csv_image_reference(row.get("img") or "")
                if not reference:
                    continue
                if reference in counts:
                    counts[reference] += 1
                    continue
                canonical_match = canonical_to_id.get(_canonicalize_image_id(reference))
                if canonical_match:
                    counts[canonical_match] += 1
                    continue
                if reference.upper().startswith("IMG_"):
                    fallback_reference = reference[4:]
                    if fallback_reference in counts:
                        counts[fallback_reference] += 1

    return counts


def _reference_count_for(image_id: str, reference_counts: dict[str, int]) -> int:
    return reference_counts.get(image_id, 0)


def _enrich_images_with_reference_counts(images: list[dict], reference_counts: dict[str, int]) -> list[dict]:
    enriched: list[dict] = []
    for image in images:
        reference_count = _reference_count_for(image["image_id"], reference_counts)
        enriched.append({
            **image,
            "reference_count": reference_count,
            "is_referenced": reference_count > 0,
        })
    return enriched


@router.get("/images/{image_id}")
def get_image(image_id: str):
    store = get_hciot_image_store()
    image = None
    for candidate_id in _candidate_image_ids(image_id):
        image = store.get_image(candidate_id)
        if image:
            break

    if not image:
        raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")

    mime = image.get("content_type") or "image/jpeg"
    return Response(content=image["data"], media_type=mime)


@admin_router.get("/")
def list_images():
    store = get_hciot_image_store()
    images = store.list_images()
    reference_counts = _build_image_reference_counts({image["image_id"] for image in images})
    return {"images": _enrich_images_with_reference_counts(images, reference_counts)}


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

    actual_image_id = _canonicalize_image_id(image_id or parsed.stem)
    store = get_hciot_image_store()

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Max 10MB allowed.")

    mime = file.content_type or mimetypes.guess_type(file.filename)[0] or "image/jpeg"

    result = store.upsert_image(actual_image_id, contents, content_type=mime)
    if not result["success"]:
        raise HTTPException(status_code=500, detail="Failed to store image in database.")

    return {
        "filename": file.filename,
        "image_id": actual_image_id,
        "url": f"/api/hciot/images/{actual_image_id}",
        "replaced": result["replaced"],
    }


@admin_router.delete("/cleanup-unused")
def delete_unused_images():
    store = get_hciot_image_store()
    images = store.list_images()
    reference_counts = _build_image_reference_counts({image["image_id"] for image in images})

    deleted_image_ids: list[str] = []
    for image in images:
        image_id = image["image_id"]
        if _reference_count_for(image_id, reference_counts) > 0:
            continue
        if store.delete_image(image_id):
            deleted_image_ids.append(image_id)

    return {
        "deleted_count": len(deleted_image_ids),
        "deleted_image_ids": deleted_image_ids,
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
