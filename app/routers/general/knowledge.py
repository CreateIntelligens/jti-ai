"""General per-store knowledge router — thin wrapper over the shared qa_kb router.

Reuses build_qa_kb_router; the shared router keys data by its ``language`` field,
which general repurposes to carry ``store_name`` (general's RAG-keying convention,
matching app/routers/general/stores.py's ``sync_to_rag(GENERAL_NAMESPACE, store_name, ...)``).
AI Q&A extraction is disabled (include_extract=False).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends

from app.auth import require_kb_access
from app.routers._shared.qa_kb_router import QaKbRouterConfig, build_qa_kb_router
from app.services.general.knowledge_store import get_general_knowledge_store
from app.services.general.topic_store import get_general_topic_store
from app.services.rag.backfill import get_backfill_service

logger = logging.getLogger(__name__)


def _invalidate_cache(_store_name: str | None = None) -> None:
    # General chat resolves RAG per request; no module-level file map to bust.
    return None


def _other_language(store_name: str) -> str:
    # General is single-language; the "other language" partner is itself (no-op).
    return store_name


# INVARIANT: general store names are lowercase by construction
# (`store_{uuid4().hex}` — see StoreRegistry._new_store_name). The knowledge
# store base lowercases the store_name key (`_normalize_language`) while the
# topic store and RAG use it raw; these only agree because the key is already
# lowercase. If store naming ever allows mixed case, normalize store_name at
# this boundary so all three layers key identically.
def _make_config() -> QaKbRouterConfig:
    return QaKbRouterConfig(
        tag="General Knowledge",
        app="general",
        knowledge_store_factory=lambda: get_general_knowledge_store(),
        topic_store_factory=lambda store_name: get_general_topic_store(store_name or ""),
        rag_source_type="general",
        invalidate_cache=_invalidate_cache,
        other_language=_other_language,
    )


router = build_qa_kb_router(_make_config(), include_knowledge=True, include_extract=False)


# ── Per-store RAG reindex ────────────────────────────────────────────────
# General partitions RAG by store_name (not zh/en), so it can't ride the
# whole-app zh/en reindex in admin_rag. Reindex one store at a time here.
# store_name is carried in the `language` query param, matching the rest of
# the general knowledge surface.
_reindex_router = APIRouter(
    tags=["General Knowledge"], dependencies=[Depends(require_kb_access("general"))]
)
_running_store_reindexes: set[str] = set()


async def _run_store_reindex(store_name: str, force: bool) -> None:
    backfill = get_backfill_service()
    loop = asyncio.get_running_loop()
    _running_store_reindexes.add(store_name)
    try:
        await loop.run_in_executor(None, backfill.run_backfill, "general", store_name, force)
    except Exception as e:  # pragma: no cover - logged, surfaced via status
        logger.error("[RAG] General reindex failed for store=%s: %s", store_name, e)
    finally:
        _running_store_reindexes.discard(store_name)


@_reindex_router.post("/reindex")
async def reindex_store(language: str, force: bool = True):
    """Reindex one general store's knowledge into RAG (store_name in `language`)."""
    asyncio.create_task(_run_store_reindex(language, force))
    return {"started": True, "source_types": ["general"], "languages": [language]}


@_reindex_router.get("/reindex-status")
def reindex_store_status(language: str):
    return {"source_type": "general", "reindexing": language in _running_store_reindexes}


router.include_router(_reindex_router)
