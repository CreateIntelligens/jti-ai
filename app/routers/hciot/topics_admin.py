"""HCIoT Topics API (flat topic_id with category prefix)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import verify_admin
from app.services.hciot.topic_store import get_hciot_topic_store

router = APIRouter(tags=["HCIoT Topics"], dependencies=[Depends(verify_admin)])

_STRIP_FIELDS = {"_id", "created_at", "updated_at"}
_FIRST_TOPIC_LABELS = {
    "常見問題",
    "faq",
    "common questions",
    "frequently asked questions",
}

public_router = APIRouter(tags=["HCIoT Topics"])


def _is_first_topic_label(labels: dict | None) -> bool:
    if not isinstance(labels, dict):
        return False
    return any(
        str(label).strip().casefold() in _FIRST_TOPIC_LABELS
        for label in labels.values()
    )


def _with_common_questions_first(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda item: 0 if _is_first_topic_label(item.get("labels")) else 1,
    )


@public_router.get("/topics")
def list_topics():
    store = get_hciot_topic_store()
    categories = store.list_categories()
    for cat in categories:
        cat["topics"] = [
            {k: v for k, v in t.items() if k not in _STRIP_FIELDS}
            for t in cat.get("topics", [])
        ]
        cat["topics"] = _with_common_questions_first(cat["topics"])
    return {"categories": _with_common_questions_first(categories)}


# ========== Request Models ==========


class BilingualLabels(BaseModel):
    zh: str
    en: str


class TopicQuestionsRequest(BaseModel):
    zh: list[str]
    en: list[str]


class CreateTopicRequest(BaseModel):
    topic_id: str
    labels: BilingualLabels
    category_labels: BilingualLabels
    questions: TopicQuestionsRequest | None = None


class UpdateTopicRequest(BaseModel):
    labels: BilingualLabels | None = None
    category_labels: BilingualLabels | None = None
    questions: TopicQuestionsRequest | None = None


# ========== Admin Endpoints ==========


@router.post("/", status_code=201)
def create_topic(request: CreateTopicRequest):
    store = get_hciot_topic_store()
    if store.get_topic(request.topic_id):
        raise HTTPException(status_code=409, detail=f"Topic '{request.topic_id}' already exists")
    data = {
        "labels": request.labels.model_dump(),
        "category_labels": request.category_labels.model_dump(),
        "questions": request.questions.model_dump() if request.questions else {"zh": [], "en": []},
    }
    store.upsert_topic(request.topic_id, data)
    return store.get_topic(request.topic_id)


@router.put("/{topic_id:path}")
def update_topic(topic_id: str, request: UpdateTopicRequest):
    store = get_hciot_topic_store()
    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    if request.labels:
        update_data["labels"] = request.labels.model_dump()
    if request.category_labels:
        update_data["category_labels"] = request.category_labels.model_dump()
    success = store.update_topic(topic_id, update_data)
    if not success:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    return store.get_topic(topic_id)


@router.delete("/{topic_id:path}")
def delete_topic(topic_id: str):
    store = get_hciot_topic_store()
    deleted = store.delete_topic(topic_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    return {"message": f"Topic '{topic_id}' deleted"}
