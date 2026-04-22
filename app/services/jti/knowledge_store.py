"""JTI-bound knowledge store facade."""

from __future__ import annotations

from app.services.knowledge_store import NamespacedKnowledgeStore, get_namespaced_knowledge_store

JTI_NAMESPACE = "jti"


def get_jti_knowledge_store() -> NamespacedKnowledgeStore:
    return get_namespaced_knowledge_store(JTI_NAMESPACE)
