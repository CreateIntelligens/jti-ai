"""ESG topic storage for standard QA workspaces."""

from __future__ import annotations

from app.services._shared.qa_kb.topic_store_base import (
    Language,
    QaKbTopicStoreBase,
    Topic,
)
from app.services.agent_utils import normalize_language
from app.services.db_names import ESG_DB_NAME

__all__ = [
    "EsgTopicStore",
    "Language",
    "Topic",
    "get_esg_topic_store",
    "to_topic_language",
]


def to_topic_language(language: str | None = None) -> Language:
    return "en" if normalize_language(language) == "en" else "zh"


class EsgTopicStore(QaKbTopicStoreBase):
    DB_NAME = ESG_DB_NAME
    COLLECTION_NAME = "esg_topics"
    CATEGORY_COLLECTION_NAME = "esg_categories"
    NAMESPACE = "esg"


_esg_topic_stores: dict[Language, EsgTopicStore] = {}


def get_esg_topic_store(language: str | None = None) -> EsgTopicStore:
    lang = to_topic_language(language)
    if lang not in _esg_topic_stores:
        _esg_topic_stores[lang] = EsgTopicStore(lang)
    return _esg_topic_stores[lang]
