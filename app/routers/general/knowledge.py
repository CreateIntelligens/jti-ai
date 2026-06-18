"""General per-store knowledge router — thin wrapper over the shared qa_kb router.

Reuses build_qa_kb_router; the shared router keys data by its ``language`` field,
which general repurposes to carry ``store_name`` (general's RAG-keying convention,
matching app/routers/general/stores.py's ``sync_to_rag(GENERAL_NAMESPACE, store_name, ...)``).
AI Q&A extraction is disabled (include_extract=False).
"""

from __future__ import annotations

from app.routers._shared.qa_kb_router import QaKbRouterConfig, build_qa_kb_router
from app.services.general.knowledge_store import get_general_knowledge_store
from app.services.general.topic_store import get_general_topic_store


def _invalidate_cache(_store_name: str | None = None) -> None:
    # General chat resolves RAG per request; no module-level file map to bust.
    return None


def _other_language(store_name: str) -> str:
    # General is single-language; the "other language" partner is itself (no-op).
    return store_name


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
