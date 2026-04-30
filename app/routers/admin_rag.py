"""Admin endpoints for generic RAG operations."""

import asyncio
import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.auth import verify_admin
from app.services.rag.backfill import get_backfill_service

logger = logging.getLogger(__name__)

LANGUAGES = ["zh", "en"]
SOURCE_TYPES = ["hciot", "jti"]

router = APIRouter(
    prefix="/api/admin/rag",
    dependencies=[Depends(verify_admin)],
)


class ReindexRequest(BaseModel):
    source_type: str = "hciot"
    force: bool = True


def _expand_source_types(source_type: str) -> list[str]:
    normalized = source_type.lower().strip()
    if normalized == "all":
        return SOURCE_TYPES.copy()
    if normalized in SOURCE_TYPES:
        return [normalized]
    raise HTTPException(status_code=400, detail="source_type must be one of: hciot, jti, all")


async def _run_rag_reindex(source_types: list[str], force: bool) -> None:
    """Run requested source/language RAG backfills without blocking the request."""
    backfill = get_backfill_service()
    loop = asyncio.get_running_loop()
    logger.info("[RAG] Reindex started for source_types=%s languages=%s force=%s", source_types, LANGUAGES, force)

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


@router.post("/reindex")
async def reindex_rag(
    source_type: str = "hciot",
    force: bool = True,
    body: ReindexRequest | None = Body(default=None),
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
