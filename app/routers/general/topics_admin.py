"""General per-store Topics API — mirrors HCIoT's topics_admin, keyed by store_name.

Each general store has its own isolated category/topic tree (carried in the
topic store base's ``language`` slot = store_name). Unlike HCIoT this is
single-language, so labels/questions are stored as plain values rather than
{zh, en} partitioned dicts. Response shapes match HCIoT's
``{categories: [{id, label, topics: [...]}]}`` so the shared front-end
QA workspace consumes general and HCIoT identically.

Topic question lists are populated from validated QA CSVs via the shared
qa_kb sync path, so only well-formed Q&A content surfaces as quick-question
buttons.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import require_kb_access
from app.services.general.topic_store import get_general_topic_store

router = APIRouter(tags=["General Topics"], dependencies=[Depends(require_kb_access("general"))])
public_router = APIRouter(tags=["General Topics"])


def _plain(value, fallback: str = "") -> str:
    """Coerce a stored label to a plain string (general is single-language).

    Tolerates legacy {zh, en} dicts by preferring zh, so the same store base
    used by HCIoT stays compatible."""
    if isinstance(value, dict):
        return str(value.get("zh") or value.get("en") or fallback)
    if value is None:
        return fallback
    return str(value)


def _plain_questions(value) -> list:
    if isinstance(value, dict):
        questions = value.get("zh") or value.get("en") or []
    else:
        questions = value or []
    return questions if isinstance(questions, list) else []


def _topic_has_public_questions(topic: dict) -> bool:
    questions = _plain_questions(topic.get("questions"))
    if not questions:
        return True
    hidden = set(_plain_questions(topic.get("hidden_questions")))
    return any(q not in hidden for q in questions)


def _localize_topic(topic: dict, filter_hidden: bool) -> dict:
    questions = _plain_questions(topic.get("questions"))
    hidden = _plain_questions(topic.get("hidden_questions"))
    payload = {
        "id": topic.get("id") or topic.get("topic_id", ""),
        "label": _plain(topic.get("labels")),
    }
    if "order" in topic:
        payload["order"] = topic["order"]
    if filter_hidden:
        payload["questions"] = [q for q in questions if q not in hidden]
    else:
        payload["questions"] = questions
        payload["hidden_questions"] = hidden
        payload["hidden"] = bool(topic.get("hidden", False))
    return payload


def _category_order(cat: dict) -> int:
    return min((t.get("order", 0) for t in cat.get("topics", [])), default=0)


def _build_categories(store_name: str, filter_hidden: bool) -> list[dict]:
    store = get_general_topic_store(store_name)
    category_meta = store.get_category_meta()
    raw_categories = store.list_categories()
    categories: list[dict] = []
    for cat in raw_categories:
        category_id = cat.get("id", "")
        category_hidden = bool(category_meta.get(category_id, {}).get("hidden", False))
        if filter_hidden and category_hidden:
            continue

        raw_topics = cat.get("topics", [])
        if filter_hidden:
            raw_topics = [
                t for t in raw_topics
                if not t.get("hidden", False) and _topic_has_public_questions(t)
            ]
        topics = [_localize_topic(t, filter_hidden) for t in raw_topics]
        if filter_hidden and not topics:
            continue

        payload = {
            "id": category_id,
            "label": _plain(cat.get("labels"), category_id),
            "order": _category_order(cat),
            "topics": topics,
        }
        if not filter_hidden:
            payload["hidden"] = category_hidden
        categories.append(payload)
    return sorted(categories, key=lambda c: c["order"])


@public_router.get("/stores/{store_name}/topics")
def list_topics_slim(store_name: str):
    """Public topic listing — filters hidden topics/questions."""
    return {"categories": _build_categories(store_name, filter_hidden=True)}


@router.get("/stores/{store_name}/topics/all")
def list_topics_all(store_name: str):
    """Unfiltered listing for admin — includes hidden questions/flags.

    Served only under the authed /api/general-admin mount: this exposes hidden
    topics/questions, so it must require KB admin access (unlike the public
    /topics slim listing which filters hidden content)."""
    return {"categories": _build_categories(store_name, filter_hidden=False)}


class CreateTopicRequest(BaseModel):
    topic_id: str
    labels: str
    category_labels: str
    questions: list[str] | None = None


class UpdateTopicRequest(BaseModel):
    labels: str | None = None
    category_labels: str | None = None
    questions: list[str] | None = None
    hidden_questions: list[str] | None = None
    hidden: bool | None = None


class UpdateCategoryVisibilityRequest(BaseModel):
    hidden: bool


class ReorderTopicsRequest(BaseModel):
    topic_ids: list[str]


class DeleteTopicsRequest(BaseModel):
    topic_ids: list[str]


@router.post("/stores/{store_name}/topics/", status_code=201)
def create_topic(store_name: str, request: CreateTopicRequest):
    store = get_general_topic_store(store_name)
    if store.get_topic(request.topic_id):
        raise HTTPException(status_code=409, detail=f"Topic '{request.topic_id}' already exists")
    store.upsert_topic(
        request.topic_id,
        {
            "labels": request.labels,
            "category_labels": request.category_labels,
            "questions": request.questions or [],
            "hidden_questions": [],
            "hidden": False,
        },
    )
    return store.get_topic(request.topic_id)


@router.put("/stores/{store_name}/topics/reorder")
def reorder_topics(store_name: str, request: ReorderTopicsRequest):
    store = get_general_topic_store(store_name)
    return {"updated": store.reorder_topics(request.topic_ids)}


@router.post("/stores/{store_name}/topics/delete-batch")
def delete_topics_batch(store_name: str, request: DeleteTopicsRequest):
    store = get_general_topic_store(store_name)
    return {"deleted": store.delete_topics(request.topic_ids)}


@router.put("/stores/{store_name}/topics/categories/{category_id}/visibility")
def update_category_visibility(
    store_name: str, category_id: str, request: UpdateCategoryVisibilityRequest
):
    store = get_general_topic_store(store_name)
    if not store.set_category_hidden(category_id, request.hidden):
        raise HTTPException(status_code=404, detail=f"Category '{category_id}' not found")
    return {"category_id": category_id, "hidden": request.hidden}


@router.put("/stores/{store_name}/topics/{topic_id:path}")
def update_topic(store_name: str, topic_id: str, request: UpdateTopicRequest):
    store = get_general_topic_store(store_name)
    update_data: dict = {}
    if request.labels is not None:
        update_data["labels"] = request.labels
    if request.category_labels is not None:
        update_data["category_labels"] = request.category_labels
    if request.questions is not None:
        update_data["questions"] = request.questions
    if request.hidden_questions is not None:
        update_data["hidden_questions"] = request.hidden_questions
    if request.hidden is not None:
        update_data["hidden"] = request.hidden
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    if not store.update_topic(topic_id, update_data):
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    return store.get_topic(topic_id)


@router.delete("/stores/{store_name}/topics/{topic_id:path}")
def delete_topic(store_name: str, topic_id: str):
    store = get_general_topic_store(store_name)
    if not store.delete_topic(topic_id):
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    return {"message": f"Topic '{topic_id}' deleted"}
