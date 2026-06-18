"""General per-store topic storage — thin subclass of the shared topic base.

The base partitions purely by ``self.language``; general passes ``store_name``
there, so each store gets its own isolated topic set. General is single-language.
"""

from __future__ import annotations

from typing import cast

from app.services._shared.qa_kb.topic_store_base import Language, QaKbTopicStoreBase


class GeneralTopicStore(QaKbTopicStoreBase):
    DB_NAME = "general_app"
    COLLECTION_NAME = "general_topics"
    CATEGORY_COLLECTION_NAME = "general_categories"
    NAMESPACE = "general"

    def __init__(self, store_name: str):
        # General partitions topics by store_name, carried in the base's
        # ``language`` slot. The base only uses it as a Mongo filter value,
        # so any string is valid here despite the Language literal hint.
        super().__init__(cast(Language, store_name))


def get_general_topic_store(store_name: str) -> GeneralTopicStore:
    """Return a topic store scoped to one general store. Not cached across
    store_names because the partition key (store_name) is the constructor arg."""
    return GeneralTopicStore(store_name)
