"""HCIoT Topics API (flat topic_id with category prefix)."""

from __future__ import annotations

from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import verify_admin
from app.services.hciot.topic_store import Language, get_hciot_topic_store
from app.utils import get_other_language

router = APIRouter(tags=["HCIoT Topics"], dependencies=[Depends(verify_admin)])

_FIRST_TOPIC_LABELS = {
    "常見問題",
    "faq",
    "common questions",
    "frequently asked questions",
}

Lang = Language

public_router = APIRouter(tags=["HCIoT Topics"])


def _label_strings(value) -> list[str]:
    if isinstance(value, dict):
        return [str(v) for v in value.values()]
    if isinstance(value, str):
        return [value]
    return []


def _is_first_topic_label(values: Iterable[str]) -> bool:
    return any(v.strip().casefold() in _FIRST_TOPIC_LABELS for v in values)


def _with_common_questions_first(items: list[dict]) -> list[dict]:
    def key(item: dict) -> int:
        labels = _label_strings(item.get("labels") or item.get("label"))
        return 0 if _is_first_topic_label(labels) else 1
    return sorted(items, key=key)


def _localized_text(value, lang: Lang, fallback: str = "") -> str:
    if isinstance(value, dict):
        return str(value.get(lang, ""))
    if value is None:
        return fallback
    return str(value)


def _localized_questions(value, lang: Lang) -> list:
    if isinstance(value, dict):
        questions = value.get(lang, [])
    else:
        questions = value or []
    return questions if isinstance(questions, list) else []


def _localize_topic(topic: dict, lang: Lang) -> dict:
    payload = {
        "id": topic.get("id") or topic.get("topic_id", ""),
        "label": _localized_text(topic.get("labels"), lang),
    }
    if "order" in topic:
        payload["order"] = topic["order"]
    payload["questions"] = _localized_questions(topic.get("questions"), lang)
    return payload


def _build_categories(language: Lang) -> list[dict]:
    """Build the single-language category tree consumed by the public endpoint."""
    store = get_hciot_topic_store(language)
    result = []
    for cat in store.list_categories():
        topics = _with_common_questions_first([
            _localize_topic(t, language) for t in cat.get("topics", [])
        ])
        result.append({
            "id": cat.get("id", ""),
            "label": _localized_text(cat.get("labels"), language, cat.get("id", "")),
            "topics": topics,
        })
    return _with_common_questions_first(result)


@public_router.get("/topics/{lang}")
def list_topics_slim(lang: Lang):
    return {"categories": _build_categories(lang)}


def _partitioned_label(value: str, language: Lang) -> dict[str, str]:
    """Store the label in the active language partition and blank the other slot."""
    return {language: value, get_other_language(language): ""}


def _partitioned_questions(value: list[str], language: Lang) -> dict[str, list[str]]:
    return {language: value, get_other_language(language): []}


class CreateTopicRequest(BaseModel):
    topic_id: str
    labels: str
    category_labels: str
    questions: list[str] | None = None


class UpdateTopicRequest(BaseModel):
    labels: str | None = None
    category_labels: str | None = None
    questions: list[str] | None = None


@router.post("/", status_code=201)
def create_topic(request: CreateTopicRequest, language: Lang = "zh"):
    store = get_hciot_topic_store(language)
    if store.get_topic(request.topic_id):
        raise HTTPException(status_code=409, detail=f"Topic '{request.topic_id}' already exists")
    data = {
        "labels": _partitioned_label(request.labels, language),
        "category_labels": _partitioned_label(request.category_labels, language),
        "questions": _partitioned_questions(request.questions or [], language),
    }
    store.upsert_topic(request.topic_id, data)
    return store.get_topic(request.topic_id)


@router.put("/{topic_id:path}")
def update_topic(topic_id: str, request: UpdateTopicRequest, language: Lang = "zh"):
    store = get_hciot_topic_store(language)
    update_data: dict = {}
    if request.labels is not None:
        update_data["labels"] = _partitioned_label(request.labels, language)
    if request.category_labels is not None:
        update_data["category_labels"] = _partitioned_label(request.category_labels, language)
    if request.questions is not None:
        update_data["questions"] = _partitioned_questions(request.questions, language)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    success = store.update_topic(topic_id, update_data)
    if not success:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    return store.get_topic(topic_id)


@router.delete("/{topic_id:path}")
def delete_topic(topic_id: str, language: Lang = "zh"):
    store = get_hciot_topic_store(language)
    deleted = store.delete_topic(topic_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    return {"message": f"Topic '{topic_id}' deleted"}
