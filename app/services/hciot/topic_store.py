"""MongoDB-backed HCIoT topic storage (flat).

Each document in `hciot_topics` represents a single topic:

  {
    "language": "en",
    "topic_id": "ortho-rehab/prp",
    "order": 0,
    "labels": { "zh": "PRP", "en": "PRP Therapy" },
    "category_labels": { "zh": "骨科＋復健科", "en": "Orthopedics & Rehab" },
    "questions": { "zh": [...], "en": [...] }
  }
"""

from __future__ import annotations

from app.services.agent_utils import normalize_language
from app.services._shared.qa_kb.topic_store_base import (
    Language,
    QaKbTopicStoreBase,
    Topic,
)


__all__ = [
    "HciotTopicStore",
    "Language",
    "Topic",
    "get_hciot_topic_store",
    "to_topic_language",
]


def to_topic_language(language: str | None = None) -> Language:
    return "en" if normalize_language(language) == "en" else "zh"


class HciotTopicStore(QaKbTopicStoreBase):
    DB_NAME = "hciot_app"
    COLLECTION_NAME = "hciot_topics"
    CATEGORY_COLLECTION_NAME = "hciot_categories"
    COLLECTION = COLLECTION_NAME
    NAMESPACE = "hciot"


_hciot_topic_stores: dict[Language, HciotTopicStore] = {}


def get_hciot_topic_store(language: str | None = None) -> HciotTopicStore:
    """Return singleton HCIoT topic store."""
    lang = to_topic_language(language)
    if lang not in _hciot_topic_stores:
        _hciot_topic_stores[lang] = HciotTopicStore(lang)
    return _hciot_topic_stores[lang]
