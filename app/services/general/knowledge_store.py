"""General per-store knowledge file storage — thin subclass of the shared qa_kb base.

The `language` argument on the base methods carries the general ``store_name``
(general's established RAG-keying convention), giving per-store isolation for free.
"""

from __future__ import annotations

from app.services._shared.qa_kb.knowledge_store_base import QaKbKnowledgeStoreBase


class GeneralKnowledgeStore(QaKbKnowledgeStoreBase):
    DB_NAME = "general_app"
    COLLECTION_NAME = "general_knowledge_files"
    NAMESPACE = "general"


_knowledge_store: GeneralKnowledgeStore | None = None


def get_general_knowledge_store() -> GeneralKnowledgeStore:
    global _knowledge_store
    if _knowledge_store is None:
        _knowledge_store = GeneralKnowledgeStore()
    return _knowledge_store
