"""
HCIoT Topics admin API.

Provides CRUD for categories and their nested topics.
All endpoints require admin authentication.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import verify_admin
from app.services.hciot.topic_store import get_hciot_topic_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["HCIoT Topics Admin"], dependencies=[Depends(verify_admin)])


# ========== Request Models ==========


class BilingualLabels(BaseModel):
    zh: str
    en: str


class CreateCategoryRequest(BaseModel):
    id: str
    labels: BilingualLabels
    order: int | None = None


class UpdateCategoryRequest(BaseModel):
    labels: BilingualLabels | None = None


class ReorderCategoriesRequest(BaseModel):
    category_ids: list[str]


class ReorderTopicsRequest(BaseModel):
    topic_ids: list[str]


class TopicQuestionsRequest(BaseModel):
    zh: list[str]
    en: list[str]


class CreateTopicRequest(BaseModel):
    id: str
    icon: str
    accent: str
    labels: BilingualLabels
    summaries: BilingualLabels
    questions: TopicQuestionsRequest


class UpdateTopicRequest(BaseModel):
    icon: str | None = None
    accent: str | None = None
    labels: BilingualLabels | None = None
    summaries: BilingualLabels | None = None
    questions: TopicQuestionsRequest | None = None


class MoveTopicRequest(BaseModel):
    to_category_id: str


# ========== Category Endpoints ==========


@router.get("/")
def list_categories():
    """List all categories with their topics."""
    store = get_hciot_topic_store()
    return {"categories": store.list_categories()}


@router.post("/", status_code=201)
def create_category(request: CreateCategoryRequest):
    """Create a new category."""
    store = get_hciot_topic_store()
    existing = store.get_category(request.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Category '{request.id}' already exists")
    categories = store.list_categories()
    data = {
        "id": request.id,
        "order": request.order if request.order is not None else len(categories),
        "labels": request.labels.model_dump(),
        "topics": [],
    }
    store.upsert_category(request.id, data)
    return store.get_category(request.id)


@router.put("/reorder")
def reorder_categories(request: ReorderCategoriesRequest):
    """Reorder categories by providing an ordered list of category IDs."""
    store = get_hciot_topic_store()
    store.reorder_categories(request.category_ids)
    return {"message": "Categories reordered", "order": request.category_ids}


@router.put("/{category_id}")
def update_category(category_id: str, request: UpdateCategoryRequest):
    """Update a category's labels."""
    store = get_hciot_topic_store()
    cat = store.get_category(category_id)
    if not cat:
        raise HTTPException(status_code=404, detail=f"Category '{category_id}' not found")
    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    store.upsert_category(category_id, {**cat, **update_data})
    return store.get_category(category_id)


@router.delete("/{category_id}")
def delete_category(category_id: str):
    """Delete a category and all its topics."""
    store = get_hciot_topic_store()
    deleted = store.delete_category(category_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Category '{category_id}' not found")
    return {"message": f"Category '{category_id}' deleted"}


# ========== Topic Endpoints ==========


@router.post("/{category_id}/topics", status_code=201)
def add_topic(category_id: str, request: CreateTopicRequest):
    """Add a topic to a category."""
    store = get_hciot_topic_store()
    cat = store.get_category(category_id)
    if not cat:
        raise HTTPException(status_code=404, detail=f"Category '{category_id}' not found")
    existing_ids = {t["id"] for t in cat.get("topics", [])}
    if request.id in existing_ids:
        raise HTTPException(status_code=409, detail=f"Topic '{request.id}' already exists")
    topic = request.model_dump()
    try:
        store.add_topic(category_id, topic)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return store.get_category(category_id)


@router.put("/{category_id}/topics/reorder")
def reorder_topics(category_id: str, request: ReorderTopicsRequest):
    """Reorder topics within a category."""
    store = get_hciot_topic_store()
    success = store.reorder_topics(category_id, request.topic_ids)
    if not success:
        raise HTTPException(status_code=404, detail=f"Category '{category_id}' not found")
    return {"message": "Topics reordered", "order": request.topic_ids}


@router.put("/{category_id}/topics/{topic_id}")
def update_topic(category_id: str, topic_id: str, request: UpdateTopicRequest):
    """Update a topic's fields."""
    store = get_hciot_topic_store()
    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    success = store.update_topic(category_id, topic_id, update_data)
    if not success:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found in category '{category_id}'")
    return store.get_category(category_id)


@router.delete("/{category_id}/topics/{topic_id}")
def delete_topic(category_id: str, topic_id: str):
    """Delete a topic from a category."""
    store = get_hciot_topic_store()
    deleted = store.delete_topic(category_id, topic_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found in category '{category_id}'")
    return {"message": f"Topic '{topic_id}' deleted from '{category_id}'"}


@router.post("/{category_id}/topics/{topic_id}/move")
def move_topic(category_id: str, topic_id: str, request: MoveTopicRequest):
    """Move a topic to a different category."""
    store = get_hciot_topic_store()
    success = store.move_topic(category_id, request.to_category_id, topic_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Topic '{topic_id}' or category not found",
        )
    return {
        "message": f"Topic '{topic_id}' moved to '{request.to_category_id}'",
        "from": category_id,
        "to": request.to_category_id,
    }
