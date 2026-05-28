"""HCIoT knowledge management API."""

from __future__ import annotations

from fastapi import BackgroundTasks

from app.auth import verify_admin
from app.routers._shared.qa_kb_router import (
    QaKbRouterConfig,
    _sync_topic_questions_from_store as _shared_sync_topic_questions_from_store,
    build_qa_kb_router,
    save_qa_csv_to_topic as _shared_save_qa_csv_to_topic,
)
from app.services.hciot.knowledge_store import get_hciot_knowledge_store
from app.services.hciot.main_agent import invalidate_hciot_file_map
from app.services.hciot.topic_store import get_hciot_topic_store
from app.utils import get_other_language


def _make_config() -> QaKbRouterConfig:
    return QaKbRouterConfig(
        tag="HCIoT Knowledge",
        auth_dep=verify_admin,
        knowledge_store_factory=lambda: get_hciot_knowledge_store(),
        topic_store_factory=lambda language: get_hciot_topic_store(language),
        rag_source_type="hciot",
        invalidate_cache=lambda language=None: invalidate_hciot_file_map(language),
        other_language=get_other_language,
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
