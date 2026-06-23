"""JTI topic storage for standard QA workspaces."""

from __future__ import annotations

from app.services._shared.qa_kb.topic_store_base import (
    Language,
    QaKbTopicStoreBase,
    Topic,
)
from app.services.agent_utils import normalize_language
from app.services.db_names import JTI_DB_NAME

__all__ = [
    "JtiTopicStore",
    "Language",
    "Topic",
    "get_jti_topic_store",
    "to_topic_language",
]


def to_topic_language(language: str | None = None) -> Language:
    return "en" if normalize_language(language) == "en" else "zh"


class JtiTopicStore(QaKbTopicStoreBase):
    DB_NAME = JTI_DB_NAME
    COLLECTION_NAME = "jti_topics"
    CATEGORY_COLLECTION_NAME = "jti_categories"
    NAMESPACE = "jti"


_jti_topic_stores: dict[Language, JtiTopicStore] = {}


def get_jti_topic_store(language: str | None = None) -> JtiTopicStore:
    lang = to_topic_language(language)
    if lang not in _jti_topic_stores:
        _jti_topic_stores[lang] = JtiTopicStore(lang)
    return _jti_topic_stores[lang]
