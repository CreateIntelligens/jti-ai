"""General per-store topics API (single-language, plain labels).

Each general store has its own isolated set of topics, keyed by store_name
(carried in the topic store base's ``language`` slot). Topics drive the
front-end "quick question" buttons. Their question lists are populated from
validated QA CSVs via the shared qa_kb sync path, so only well-formed Q&A
content surfaces as quick-question buttons.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import require_kb_access
from app.services.general.topic_store import get_general_topic_store

router = APIRouter(tags=["General Topics"], dependencies=[Depends(require_kb_access("general"))])
public_router = APIRouter(tags=["General Topics"])


class CreateTopicRequest(BaseModel):
    id: str
    label: str
    questions: list[str] = []


class UpdateTopicRequest(BaseModel):
    label: str | None = None
    questions: list[str] | None = None
    hidden_questions: list[str] | None = None


class ReorderTopicsRequest(BaseModel):
    topic_ids: list[str]


class DeleteTopicsRequest(BaseModel):
    topic_ids: list[str]


def _public_topic(topic: dict) -> dict:
    hidden = topic.get("hidden_questions") or []
    return {
        "id": topic.get("topic_id", ""),
        "label": topic.get("labels", ""),
        "order": topic.get("order"),
        "questions": [q for q in (topic.get("questions") or []) if q not in hidden],
    }


@public_router.get("/stores/{store_name}/topics")
def list_public_topics(store_name: str):
    store = get_general_topic_store(store_name)
    return [_public_topic(t) for t in store.list_topics()]


@router.post("/stores/{store_name}/topics/", status_code=201)
def create_topic(store_name: str, request: CreateTopicRequest):
    store = get_general_topic_store(store_name)
    store.upsert_topic(request.id, {"labels": request.label, "questions": request.questions})
    return {"ok": True, "id": request.id}


@router.put("/stores/{store_name}/topics/reorder")
def reorder_topics(store_name: str, request: ReorderTopicsRequest):
    store = get_general_topic_store(store_name)
    return {"updated": store.reorder_topics(request.topic_ids)}


@router.post("/stores/{store_name}/topics/delete-batch")
def delete_topics(store_name: str, request: DeleteTopicsRequest):
    store = get_general_topic_store(store_name)
    return {"deleted": store.delete_topics(request.topic_ids)}


@router.put("/stores/{store_name}/topics/{topic_id:path}")
def update_topic(store_name: str, topic_id: str, request: UpdateTopicRequest):
    store = get_general_topic_store(store_name)
    data = {k: v for k, v in request.model_dump().items() if v is not None}
    if "label" in data:
        data["labels"] = data.pop("label")
    if not store.update_topic(topic_id, data):
        raise HTTPException(status_code=404, detail="topic not found")
    return {"ok": True}


@router.delete("/stores/{store_name}/topics/{topic_id:path}")
def delete_topic(store_name: str, topic_id: str):
    store = get_general_topic_store(store_name)
    if not store.delete_topic(topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    return {"ok": True}
