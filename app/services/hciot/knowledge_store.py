"""HCIoT knowledge file storage — thin subclass of the shared qa_kb base."""

from __future__ import annotations

from app.services._shared.qa_kb.knowledge_store_base import QaKbKnowledgeStoreBase


class HciotKnowledgeStore(QaKbKnowledgeStoreBase):
    DB_NAME = "hciot_app"
    COLLECTION_NAME = "knowledge_files"
    NAMESPACE = "hciot"


_knowledge_store: HciotKnowledgeStore | None = None


def get_hciot_knowledge_store() -> HciotKnowledgeStore:
    global _knowledge_store
    if _knowledge_store is None:
        _knowledge_store = HciotKnowledgeStore()
    return _knowledge_store
