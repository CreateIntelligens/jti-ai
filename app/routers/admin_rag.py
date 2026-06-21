"""Admin endpoints for generic RAG operations."""

import asyncio
import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.auth import KB_ACCESS_DENIED_DETAIL, can_access_kb, verify_admin, verify_auth
from app.services.rag.backfill import get_backfill_service

logger = logging.getLogger(__name__)

LANGUAGES = ["zh", "en"]
SOURCE_TYPES = ["hciot", "jti", "esg"]

router = APIRouter(prefix="/api/admin/rag")


class ReindexRequest(BaseModel):
    source_type: str = "hciot"
    force: bool = True


def _expand_source_types(source_type: str) -> list[str]:
    normalized = source_type.lower().strip()
    if normalized == "all":
        return SOURCE_TYPES.copy()
    if normalized in SOURCE_TYPES:
        return [normalized]
    raise HTTPException(status_code=400, detail="source_type must be one of: hciot, jti, esg, all")


def _require_status_access(auth: dict, source_types: list[str]) -> None:
    if all(can_access_kb(auth, source) for source in source_types):
        return
    raise HTTPException(status_code=403, detail=KB_ACCESS_DENIED_DETAIL)


_running_reindexes = set()


async def _run_rag_reindex(source_types: list[str], force: bool) -> None:
    """Run requested source/language RAG backfills without blocking the request."""
    backfill = get_backfill_service()
    loop = asyncio.get_running_loop()
    logger.info("[RAG] Reindex started for source_types=%s languages=%s force=%s", source_types, LANGUAGES, force)

    active_keys = {(st, lang) for st in source_types for lang in LANGUAGES}
    _running_reindexes.update(active_keys)

    try:
        tasks = [
            loop.run_in_executor(None, backfill.run_backfill, source_type, language, force)
            for source_type in source_types
            for language in LANGUAGES
        ]
        await asyncio.gather(*tasks)
        logger.info("[RAG] Reindex finished for source_types=%s languages=%s", source_types, LANGUAGES)
    except Exception as e:
        logger.error("[RAG] Reindex failed: %s", e)
    finally:
        _running_reindexes.difference_update(active_keys)


@router.post("/reindex")
async def reindex_rag(
    source_type: str = "hciot",
    force: bool = True,
    body: ReindexRequest | None = Body(default=None),
    _auth: dict = Depends(verify_admin),
):
    requested_source_type = body.source_type if body else source_type
    requested_force = body.force if body else force
    source_types = _expand_source_types(requested_source_type)

    asyncio.create_task(_run_rag_reindex(source_types, requested_force))

    return {
        "started": True,
        "source_types": source_types,
        "languages": LANGUAGES,
    }


@router.get("/status")
async def reindex_status(source_type: str = "hciot", auth: dict = Depends(verify_auth)):
    source_types = _expand_source_types(source_type)
    _require_status_access(auth, source_types)
    is_running = any((st, lang) in _running_reindexes for st in source_types for lang in LANGUAGES)
    return {
        "source_type": source_type,
        "reindexing": is_running,
    }
