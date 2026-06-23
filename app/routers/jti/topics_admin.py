"""JTI standard QA Topics API."""

from __future__ import annotations

from app.routers._shared.plain_topics_admin import (
    CreateTopicRequest,
    DeleteTopicsRequest,
    ReorderTopicsRequest,
    UpdateCategoryVisibilityRequest,
    UpdateTopicRequest,
    build_plain_topics_admin,
)
from app.services.jti.knowledge_store import get_jti_knowledge_store
from app.services.jti.topic_store import Language, get_jti_topic_store

# JTI ships its Q&A as CSVs already in the knowledge store (no data/jti seed file),
# so instead of seeding from disk we fold the untagged CSVs into a single
# "常見問題" topic — the merged-csv "文件" view then renders them as one table.
_api = build_plain_topics_admin(
    app="jti",
    tag="JTI Topics",
    get_topic_store=lambda language: get_jti_topic_store(language),
    get_knowledge_store=lambda: get_jti_knowledge_store(),
    adopt_orphan_csvs=True,
)

router = _api.router
public_router = _api.public_router
list_topics_slim = _api.list_topics_slim
list_topics_all = _api.list_topics_all
create_topic = _api.create_topic
reorder_topics = _api.reorder_topics
delete_topics_batch = _api.delete_topics_batch
update_category_visibility = _api.update_category_visibility
update_topic = _api.update_topic
delete_topic = _api.delete_topic

__all__ = [
    "CreateTopicRequest",
    "DeleteTopicsRequest",
    "Language",
    "ReorderTopicsRequest",
    "UpdateCategoryVisibilityRequest",
    "UpdateTopicRequest",
    "create_topic",
    "delete_topic",
    "delete_topics_batch",
    "get_jti_topic_store",
    "list_topics_all",
    "list_topics_slim",
    "public_router",
    "reorder_topics",
    "router",
    "update_category_visibility",
    "update_topic",
]
