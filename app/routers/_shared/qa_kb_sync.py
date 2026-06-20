"""Sync helpers for QA knowledge-base workspaces."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services._shared.qa_kb.csv_utils import (
    _dedupe_non_empty,
    extract_questions_from_csv,
    merge_csv_files,
)

if TYPE_CHECKING:
    from app.routers._shared.qa_kb_router import QaKbRouterConfig

logger = logging.getLogger(__name__)


def _get_topic_hidden_questions(topic: dict | None, language: str) -> list[str]:
    """Retrieve hidden questions for a specific language from a topic dictionary."""
    if not topic:
        return []
    hidden = topic.get("hidden_questions")
    # Single-language stores (general) store a flat list; multi-language stores
    # (hciot/jti) store a {zh, en} partition dict.
    if isinstance(hidden, dict):
        hidden = hidden.get(language)
    if not isinstance(hidden, list):
        return []
    return [item for item in hidden if isinstance(item, str)]


def _existing_topic_questions(config: QaKbRouterConfig, language: str, topic_id: str | None) -> set[str]:
    if not topic_id:
        return set()
    docs = config.knowledge_store_factory().get_topic_csv_files(language, topic_id)
    seen: set[str] = set()
    for doc in docs:
        seen.update(
            question.strip()
            for question in extract_questions_from_csv(doc.get("data") or b"") or []
            if question.strip()
        )
    return seen


def _sync_topic_questions_for_doc(config: QaKbRouterConfig, language: str, doc: dict | None) -> bool:
    if not doc:
        return False
    return _sync_topic_questions_from_store(
        config,
        language=language,
        topic_id=doc.get("topic_id"),
        topic_label=doc.get("topic_label"),
        category_label=doc.get("category_label"),
    )


def _sync_topic_questions_from_store(
    config: QaKbRouterConfig,
    *,
    language: str,
    topic_id: str | None,
    topic_label: str | None,
    category_label: str | None,
    hidden_questions: list[str] | None = None,
) -> bool:
    """Merge question lists from all topic CSV files and sync topic store."""
    if not topic_id or "/" not in topic_id:
        return False

    store = config.knowledge_store_factory()
    docs = store.get_topic_csv_files(language, topic_id)

    # Order questions exactly like the merged admin view (global sort by the
    # `index` column across all files). Concatenating per file would lose the
    # cross-file order for topics split into per-image `_IMG_` CSVs.
    merged_rows = merge_csv_files(
        [doc.get("data") or b"" for doc in docs],
        [doc.get("filename") or "" for doc in docs],
    )
    questions = _dedupe_non_empty(row.get("q") for row in merged_rows)

    topic_store = config.topic_store_factory(language)
    prefix, suffix = topic_id.split("/", 1)
    current_questions = set(questions)

    def _resolve_hidden(existing_topic: dict | None) -> list[str]:
        existing_hidden = _get_topic_hidden_questions(existing_topic, language)
        if hidden_questions is not None:
            combined = set(existing_hidden).union(hidden_questions)
            return [q for q in questions if q in combined]
        return [q for q in existing_hidden if q in current_questions]

    existing = topic_store.get_topic(topic_id)
    other_lang = config.other_language(language)
    # Single-language stores (e.g. general, where `language` carries store_name)
    # report `other_language(language) == language`. There bilingual partition
    # dicts would collapse to a single key and lose data, so write flat values
    # the single-language read path expects. Multi-language stores (hciot/jti)
    # keep the {zh, en} partition.
    single_language = other_lang == language

    def _partition(value, empty):
        return value if single_language else {language: value, other_lang: empty}

    if existing:
        if not questions and not store.has_non_csv_files(language, topic_id):
            topic_store.delete_topic(topic_id)
            logger.info("[QA KB] Deleted empty topic %s", topic_id)
        else:
            if single_language:
                update = {
                    "questions": questions,
                    "hidden_questions": _resolve_hidden(existing),
                }
            else:
                update = {
                    f"questions.{language}": questions,
                    f"hidden_questions.{language}": _resolve_hidden(existing),
                }
            topic_store.update_topic(topic_id, update)
            logger.info("[QA KB] Synced %d questions -> %s", len(questions), topic_id)
        return True

    if not questions:
        return False

    topic_label_resolved = (topic_label or "").strip() or suffix
    category_label_resolved = (category_label or "").strip() or prefix
    topic_store.upsert_topic(
        topic_id,
        {
            "labels": _partition(topic_label_resolved, ""),
            "category_labels": _partition(category_label_resolved, ""),
            "questions": _partition(questions, []),
            "hidden_questions": _partition(_resolve_hidden(None), []),
        },
    )
    logger.info("[QA KB] Synced %d questions -> %s", len(questions), topic_id)
    return True
