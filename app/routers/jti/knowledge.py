"""JTI knowledge management API backed by the shared QA workspace router."""

from __future__ import annotations

from fastapi import BackgroundTasks

from app.routers._shared.qa_kb_router import QaKbRouterConfig, build_qa_kb_router
from app.routers._shared.qa_kb_sync import (
    _sync_topic_questions_from_store as _shared_sync_topic_questions_from_store,
)
from app.routers._shared.qa_kb_upload import (
    save_qa_csv_to_topic as _shared_save_qa_csv_to_topic,
)
from app.services.jti.knowledge_store import get_jti_knowledge_store
from app.services.jti.topic_store import get_jti_topic_store

SOURCE_TYPE = "jti"


def _single_language_partner(language: str) -> str:
    # JTI topics are partitioned by language in Mongo. Inside each partition the
    # topic shape is plain General-style strings/lists, not HCIoT bilingual dicts.
    return language


def _invalidate_cache(_language: str | None = None) -> None:
    return None


def _make_config() -> QaKbRouterConfig:
    return QaKbRouterConfig(
        tag="JTI Knowledge",
        app="jti",
        knowledge_store_factory=lambda: get_jti_knowledge_store(),
        topic_store_factory=lambda language: get_jti_topic_store(language),
        rag_source_type=SOURCE_TYPE,
        invalidate_cache=_invalidate_cache,
        other_language=_single_language_partner,
    )


def save_qa_csv_to_topic(
    *,
    background_tasks: BackgroundTasks,
    language: str,
    csv_bytes: bytes,
    filename: str,
    content_type: str,
    editable: bool,
    topic_id: str | None,
    category_label: str | None,
    topic_label: str | None,
    hidden_questions: list[str] | None,
) -> dict:
    return _shared_save_qa_csv_to_topic(
        config=_make_config(),
        background_tasks=background_tasks,
        language=language,
        csv_bytes=csv_bytes,
        filename=filename,
        content_type=content_type,
        editable=editable,
        topic_id=topic_id,
        category_label=category_label,
        topic_label=topic_label,
        hidden_questions=hidden_questions,
    )


def _sync_topic_questions_from_store(
    *,
    language: str,
    topic_id: str | None,
    topic_label: str | None,
    category_label: str | None,
    hidden_questions: list[str] | None = None,
) -> bool:
    return _shared_sync_topic_questions_from_store(
        _make_config(),
        language=language,
        topic_id=topic_id,
        topic_label=topic_label,
        category_label=category_label,
        hidden_questions=hidden_questions,
    )


router = build_qa_kb_router(_make_config(), include_knowledge=True, include_extract=False)
