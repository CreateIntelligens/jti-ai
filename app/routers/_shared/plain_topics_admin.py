"""Plain single-language topic admin router for fixed QA knowledge apps.

This is the General topic shape adapted to fixed managed apps that partition by
language at the document level. Each topic document stores plain strings/lists
inside its zh/en partition; it deliberately does not use HCIoT's bilingual
``{zh, en}`` fields.
"""

from __future__ import annotations

import logging
import os
import re
import time
import unicodedata
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import require_kb_access
from app.services._shared.qa_kb.csv_utils import (
    _parse_csv_rows,
    extract_questions_from_csv,
    normalize_qa_csv_rows,
)

logger = logging.getLogger(__name__)

Lang = Literal["zh", "en"]

# 公開 topics 端點（每次聊天頁載入都打）的 read path 量測開關。預設關閉、零開銷；
# 設 PLAIN_TOPICS_TIMING=1 才會逐段量 perf_counter 並 log，用來定位瓶頸而不臆測。
# 這是診斷工具，不改任何行為。
_TIMING_ENABLED = os.getenv("PLAIN_TOPICS_TIMING") == "1"


@contextmanager
def _timed(label: str, **ctx: object):
    if not _TIMING_ENABLED:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        detail = " ".join(f"{k}={v}" for k, v in ctx.items())
        logger.info("plain_topics_timing %s %s elapsed_ms=%.2f", label, detail, elapsed_ms)


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


@dataclass(frozen=True)
class PlainTopicsAdmin:
    router: APIRouter
    public_router: APIRouter
    list_topics_slim: Callable[[Lang], dict]
    list_topics_all: Callable[[Lang], dict]
    create_topic: Callable[[Lang, CreateTopicRequest], dict]
    reorder_topics: Callable[[Lang, ReorderTopicsRequest], dict]
    delete_topics_batch: Callable[[Lang, DeleteTopicsRequest], dict]
    update_category_visibility: Callable[[Lang, str, UpdateCategoryVisibilityRequest], dict]
    update_topic: Callable[[Lang, str, UpdateTopicRequest], dict]
    delete_topic: Callable[[Lang, str], dict]


def _to_lang(language: str | None = None) -> Lang:
    return "en" if (language or "").strip().lower().startswith("en") else "zh"


def _plain(value, fallback: str = "") -> str:
    if isinstance(value, dict):
        return str(value.get("zh") or value.get("en") or fallback)
    if value is None:
        return fallback
    return str(value)


def _plain_questions(value) -> list[str]:
    if isinstance(value, dict):
        questions = value.get("zh") or value.get("en") or []
    else:
        questions = value or []
    if not isinstance(questions, list):
        return []
    return [item for item in questions if isinstance(item, str)]


def _topic_has_public_questions(topic: dict) -> bool:
    questions = _plain_questions(topic.get("questions"))
    if not questions:
        return True
    hidden = set(_plain_questions(topic.get("hidden_questions")))
    return any(question not in hidden for question in questions)


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
        payload["questions"] = [question for question in questions if question not in set(hidden)]
    else:
        payload["questions"] = questions
        payload["hidden_questions"] = hidden
        payload["hidden"] = bool(topic.get("hidden", False))
    return payload


def _category_order(category: dict) -> int:
    return min((topic.get("order", 0) for topic in category.get("topics", [])), default=0)


def _read_category_inputs(store) -> tuple[dict[str, dict], list[dict]]:
    with ThreadPoolExecutor(max_workers=2) as executor:
        category_meta_future = executor.submit(store.get_category_meta)
        categories_future = executor.submit(store.list_categories)
        return category_meta_future.result(), categories_future.result()


def _seed_filename(language: Lang) -> str:
    return "KIOSK_QA_English.csv" if language == "en" else "KIOSK_QA_中文.csv"


def _default_seed_category(language: Lang) -> str:
    return "FAQ" if language == "en" else "常見問題"


def _slugify(value: str, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    slug = re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE).strip("-")
    return slug or fallback


@dataclass(frozen=True)
class SeedTopic:
    topic_id: str
    payload: dict
    csv_filename: str
    csv_bytes: bytes
    category_label: str
    topic_label: str


def _load_seed_topics(seed_data_root: Path, app_slug: str, language: Lang) -> list[SeedTopic]:
    seed_filename = _seed_filename(language)
    seed_path = seed_data_root / app_slug / seed_filename
    if not seed_path.exists():
        return []

    raw_bytes = seed_path.read_bytes()
    parsed = _parse_csv_rows(raw_bytes)
    if parsed is None:
        return []
    fieldnames, rows = parsed
    if "q" not in fieldnames:
        return []

    # 扁平一層：不依 CSV 的【分類】前綴拆層，所有 Q&A 全部放進單一預設分類/主題。
    # （label 必須是 {"zh","en"} dict — base store 的 list_categories 讀 dict.zh/en；
    #  之前寫純字串導致前端顯示 None。）
    questions: list[str] = []
    for row in rows:
        raw_question = (row.get("q") or "").strip()
        if not raw_question:
            continue
        if raw_question not in questions:
            questions.append(raw_question)

    if not questions:
        return []

    label = _default_seed_category(language)
    label_dict = {"zh": "常見問題", "en": "FAQ"}
    category_id = _slugify(label, "faq")
    topic_id = f"{category_id}/{category_id}"
    # Normalize to the canonical q/a/... CSV shape so the seeded knowledge file
    # matches what an upload would produce (merge_csv_files / topic sync rely on it).
    csv_bytes = normalize_qa_csv_rows(raw_bytes) or raw_bytes
    return [
        SeedTopic(
            topic_id=topic_id,
            payload={
                "labels": label_dict,
                "category_labels": label_dict,
                "questions": questions,
                "hidden_questions": [],
                "hidden": False,
                "order": 0,
            },
            csv_filename=seed_filename,
            csv_bytes=csv_bytes,
            category_label=label,
            topic_label=label,
        )
    ]


def _adopt_orphan_csvs(language: Lang, store, knowledge_store) -> None:
    """Fold every untagged CSV already in the knowledge store into a single
    "常見問題" topic, so the "文件" view renders them as one Q&A 整合 table
    (same shape as ESG's seeded topic) instead of a folder of raw CSVs.

    Used by fixed apps (JTI) that ship CSVs directly in the knowledge store
    rather than a ``data/<app>/KIOSK_QA_*.csv`` seed file. Idempotent: orphans
    are CSVs with no ``topic_id``; once tagged they're skipped on re-run.
    """
    # Cheap O(1) preflight: in steady state there are no orphans, so skip pulling
    # the entire file list (the dominant cost of this read path). Falls back to
    # the full scan if the store predates this method.
    has_orphans = getattr(knowledge_store, "has_orphan_csv_files", None)
    if callable(has_orphans):
        with _timed("adopt.has_orphan_csv_files", lang=language):
            if not has_orphans(language):
                return

    label = _default_seed_category(language)
    label_dict = {"zh": "常見問題", "en": "FAQ"}
    category_id = _slugify(label, "faq")
    topic_id = f"{category_id}/{category_id}"

    with _timed("adopt.list_files", lang=language):
        all_files = knowledge_store.list_files(language)
    orphans = [
        file
        for file in all_files
        if (file.get("filename") or "").lower().endswith(".csv") and not file.get("topic_id")
    ]
    if not orphans:
        return

    questions: list[str] = []
    for file in orphans:
        doc = knowledge_store.get_file(language, file["filename"])
        data = doc.get("data") if doc else None
        for question in (extract_questions_from_csv(data) or []) if data else []:
            if question not in questions:
                questions.append(question)
        knowledge_store.update_file_metadata(
            language,
            file["filename"],
            {"topic_id": topic_id, "category_label": label, "topic_label": label},
        )

    existing = store.get_topic(topic_id)
    payload = {
        "labels": label_dict,
        "category_labels": label_dict,
        "questions": questions,
        "hidden_questions": [],
        "hidden": False,
        "order": 0,
    }
    if existing:
        store.update_topic(topic_id, {"questions": questions})
    else:
        store.upsert_topic(topic_id, payload)


def build_plain_topics_admin(
    *,
    app: str,
    tag: str,
    get_topic_store: Callable[[str | None], object],
    seed_app_slug: str | None = None,
    seed_data_root: Callable[[], Path] | None = None,
    get_knowledge_store: Callable[[], object] | None = None,
    adopt_orphan_csvs: bool = False,
) -> PlainTopicsAdmin:
    router = APIRouter(tags=[tag], dependencies=[Depends(require_kb_access(app))])
    public_router = APIRouter(tags=[tag])

    def _seed_knowledge_csv(language: Lang, seed: SeedTopic) -> None:
        """Bind the seed CSV to its topic in the knowledge store so the merged-csv
        view renders it as a single "Q&A 整合" table (same as an uploaded topic CSV).
        Idempotent: skip if a CSV is already associated with this topic."""
        if get_knowledge_store is None:
            return
        knowledge_store = get_knowledge_store()
        if knowledge_store.get_topic_csv_files(language, seed.topic_id):
            return
        # Adopt a pre-existing untagged copy of the seed CSV instead of inserting a
        # duplicate — otherwise the orphan would still surface in the "文件" folder.
        existing = knowledge_store.get_file(language, seed.csv_filename)
        if existing is not None and not existing.get("topic_id"):
            knowledge_store.update_file_metadata(
                language,
                seed.csv_filename,
                {
                    "topic_id": seed.topic_id,
                    "category_label": seed.category_label,
                    "topic_label": seed.topic_label,
                },
            )
            return
        knowledge_store.insert_file(
            language=language,
            filename=seed.csv_filename,
            data=seed.csv_bytes,
            display_name=seed.csv_filename,
            content_type="text/csv",
            editable=True,
            topic_id=seed.topic_id,
            category_label=seed.category_label,
            topic_label=seed.topic_label,
        )

    def ensure_seed_topics(language: Lang, store) -> None:
        if adopt_orphan_csvs and get_knowledge_store is not None:
            with _timed("adopt_orphan_csvs", app=app, lang=language):
                _adopt_orphan_csvs(language, store, get_knowledge_store())
            return
        if seed_app_slug is None or seed_data_root is None:
            return
        with _timed("load_seed_topics", app=app, lang=language):
            seeds = _load_seed_topics(seed_data_root(), seed_app_slug, language)
        if not seeds:
            return

        with _timed("seed_store_list_topics", app=app, lang=language):
            existing_topic_ids = {topic.get("topic_id") for topic in store.list_topics()}
        should_create_seed_topics = not existing_topic_ids
        with _timed("seed_knowledge_csv", app=app, lang=language, seeds=len(seeds)):
            for seed in seeds:
                if should_create_seed_topics:
                    store.upsert_topic(seed.topic_id, seed.payload)
                    _seed_knowledge_csv(language, seed)
                elif seed.topic_id in existing_topic_ids:
                    _seed_knowledge_csv(language, seed)

    def build_categories(language: Lang, filter_hidden: bool) -> list[dict]:
        with _timed("build_categories.total", app=app, lang=language, filter_hidden=filter_hidden):
            store = get_topic_store(language)
            with _timed("ensure_seed_topics", app=app, lang=language):
                ensure_seed_topics(language, store)
            with _timed("read_category_inputs", app=app, lang=language):
                category_meta, raw_categories = _read_category_inputs(store)
            return _build_categories_inner(language, filter_hidden, category_meta, raw_categories)

    def _build_categories_inner(
        language: Lang,
        filter_hidden: bool,
        category_meta: dict,
        raw_categories: list[dict],
    ) -> list[dict]:
        categories: list[dict] = []
        for category in raw_categories:
            category_id = category.get("id", "")
            category_hidden = bool(category_meta.get(category_id, {}).get("hidden", False))
            if filter_hidden and category_hidden:
                continue

            raw_topics = category.get("topics", [])
            if filter_hidden:
                raw_topics = [
                    topic
                    for topic in raw_topics
                    if not topic.get("hidden", False) and _topic_has_public_questions(topic)
                ]
            topics = [_localize_topic(topic, filter_hidden) for topic in raw_topics]
            if filter_hidden and not topics:
                continue

            payload = {
                "id": category_id,
                "label": _plain(category.get("labels"), category_id),
                "order": _category_order(category),
                "topics": topics,
            }
            if not filter_hidden:
                payload["hidden"] = category_hidden
            categories.append(payload)
        return sorted(categories, key=lambda item: item["order"])

    @public_router.get("/topics/{lang}")
    def list_topics_slim(lang: Lang):
        return {"categories": build_categories(_to_lang(lang), filter_hidden=True)}

    @public_router.get("/topics/{lang}/all")
    def list_topics_all(lang: Lang):
        return {"categories": build_categories(_to_lang(lang), filter_hidden=False)}

    @router.post("/{language}/", status_code=201)
    def create_topic(language: Lang, request: CreateTopicRequest):
        lang = _to_lang(language)
        store = get_topic_store(lang)
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

    @router.put("/{language}/reorder")
    def reorder_topics(language: Lang, request: ReorderTopicsRequest):
        store = get_topic_store(_to_lang(language))
        return {"updated": store.reorder_topics(request.topic_ids)}

    @router.post("/{language}/delete-batch")
    def delete_topics_batch(language: Lang, request: DeleteTopicsRequest):
        store = get_topic_store(_to_lang(language))
        return {"deleted": store.delete_topics(request.topic_ids)}

    @router.put("/categories/{language}/{category_id}/visibility")
    def update_category_visibility(language: Lang, category_id: str, request: UpdateCategoryVisibilityRequest):
        store = get_topic_store(_to_lang(language))
        if not store.set_category_hidden(category_id, request.hidden):
            raise HTTPException(status_code=404, detail=f"Category '{category_id}' not found")
        return {"category_id": category_id, "hidden": request.hidden}

    @router.put("/{language}/{topic_id:path}")
    def update_topic(language: Lang, topic_id: str, request: UpdateTopicRequest):
        store = get_topic_store(_to_lang(language))
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

    @router.delete("/{language}/{topic_id:path}")
    def delete_topic(language: Lang, topic_id: str):
        store = get_topic_store(_to_lang(language))
        if not store.delete_topic(topic_id):
            raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
        return {"message": f"Topic '{topic_id}' deleted"}

    return PlainTopicsAdmin(
        router=router,
        public_router=public_router,
        list_topics_slim=list_topics_slim,
        list_topics_all=list_topics_all,
        create_topic=create_topic,
        reorder_topics=reorder_topics,
        delete_topics_batch=delete_topics_batch,
        update_category_visibility=update_category_visibility,
        update_topic=update_topic,
        delete_topic=delete_topic,
    )
