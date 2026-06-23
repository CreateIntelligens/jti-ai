"""JTI-bound QA knowledge store facade."""

from __future__ import annotations

from app.services._shared.qa_kb.knowledge_store_base import QaKbKnowledgeStoreBase
from app.services.db_names import JTI_DB_NAME

JTI_NAMESPACE = "jti"


class JtiKnowledgeStore(QaKbKnowledgeStoreBase):
    DB_NAME = JTI_DB_NAME
    COLLECTION_NAME = "knowledge_files"
    NAMESPACE = JTI_NAMESPACE


_knowledge_store: JtiKnowledgeStore | None = None


def get_jti_knowledge_store() -> JtiKnowledgeStore:
    global _knowledge_store
    if _knowledge_store is None:
        _knowledge_store = JtiKnowledgeStore()
    return _knowledge_store
