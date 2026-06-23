"""ESG-bound QA knowledge store facade.

ESG knowledge files already live in the shared legacy ``jti_app.knowledge_files``
collection with ``namespace='esg'``. This facade preserves that storage location
while exposing the topic-aware helpers required by the shared QA workspace.
"""

from __future__ import annotations

from app.services._shared.qa_kb.knowledge_store_base import QaKbKnowledgeStoreBase
from app.services.db_names import JTI_DB_NAME

ESG_NAMESPACE = "esg"


class EsgKnowledgeStore(QaKbKnowledgeStoreBase):
    DB_NAME = JTI_DB_NAME
    COLLECTION_NAME = "knowledge_files"
    NAMESPACE = ESG_NAMESPACE


_knowledge_store: EsgKnowledgeStore | None = None


def get_esg_knowledge_store() -> EsgKnowledgeStore:
    global _knowledge_store
    if _knowledge_store is None:
        _knowledge_store = EsgKnowledgeStore()
    return _knowledge_store
