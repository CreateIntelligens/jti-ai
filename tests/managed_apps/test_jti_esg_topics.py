from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tests.support.app_test_support import get_test_app, install_app_import_mocks

install_app_import_mocks()


class FakePlainTopicStore:
    def __init__(self, language: str = "zh", root: "FakePlainTopicStore | None" = None):
        self.language = language
        if root is not None:
            self._root = root
            return
        self._root = self
        self.topics: dict[tuple[str, str], dict] = {}
        self.category_meta_by_language: dict[str, dict[str, dict]] = {}
        self.calls: list[tuple] = []

    def bind(self, language: str = "zh"):
        return FakePlainTopicStore(language, self._root)

    def list_topics(self):
        root = self._root
        root.calls.append(("list_topics", self.language))
        return [
            {"topic_id": topic_id, **topic}
            for (lang, topic_id), topic in root.topics.items()
            if lang == self.language
        ]

    def get_topic(self, topic_id: str):
        root = self._root
        root.calls.append(("get_topic", topic_id, self.language))
        topic = root.topics.get((self.language, topic_id))
        return None if topic is None else {"topic_id": topic_id, **topic}

    def upsert_topic(self, topic_id: str, data: dict) -> None:
        root = self._root
        root.calls.append(("upsert_topic", topic_id, self.language))
        root.topics[(self.language, topic_id)] = dict(data)

    def update_topic(self, topic_id: str, data: dict) -> bool:
        root = self._root
        root.calls.append(("update_topic", topic_id, self.language))
        key = (self.language, topic_id)
        if key not in root.topics:
            return False
        root.topics[key].update(data)
        return True

    def list_categories(self):
        root = self._root
        root.calls.append(("list_categories", self.language))
        groups: dict[str, dict] = {}
        for (lang, topic_id), topic in root.topics.items():
            if lang != self.language:
                continue
            category_id = topic_id.split("/", 1)[0]
            group = groups.setdefault(
                category_id,
                {
                    "id": category_id,
                    "labels": topic.get("category_labels", category_id),
                    "topics": [],
                },
            )
            group["topics"].append({"id": topic_id, "topic_id": topic_id, **topic})
        return sorted(groups.values(), key=lambda item: item["id"])

    def get_category_meta(self):
        root = self._root
        root.calls.append(("get_category_meta", self.language))
        return {
            category_id: dict(meta)
            for category_id, meta in root.category_meta_by_language.get(self.language, {}).items()
        }

    def delete_topics(self, topic_ids: list[str]) -> int:
        root = self._root
        root.calls.append(("delete_topics", topic_ids, self.language))
        deleted = 0
        for topic_id in topic_ids:
            deleted += int(root.topics.pop((self.language, topic_id), None) is not None)
        return deleted

    def set_category_hidden(self, category_id: str, hidden: bool) -> bool:
        root = self._root
        root.calls.append(("set_category_hidden", category_id, hidden, self.language))
        root.category_meta_by_language.setdefault(self.language, {}).setdefault(category_id, {})["hidden"] = hidden
        return True


class FakePlainKnowledgeStore:
    def __init__(self):
        self.files: dict[tuple[str, str], dict] = {}
        self.calls: list[tuple] = []

    def insert_file(
        self,
        *,
        language: str,
        filename: str,
        data: bytes,
        display_name: str | None = None,
        content_type: str = "application/octet-stream",
        editable: bool = True,
        topic_id: str | None = None,
        category_label: str | None = None,
        topic_label: str | None = None,
    ):
        self.calls.append(("insert_file", language, filename, topic_id))
        doc = {
            "name": filename,
            "filename": filename,
            "display_name": display_name or filename,
            "content_type": content_type,
            "editable": editable,
            "topic_id": topic_id,
            "category_label": category_label,
            "topic_label": topic_label,
            "data": data,
            "size": len(data),
        }
        self.files[(language, filename)] = doc
        return dict(doc)

    def get_file(self, language: str, filename: str):
        self.calls.append(("get_file", language, filename))
        doc = self.files.get((language, filename))
        return None if doc is None else dict(doc)

    def list_files(self, language: str, **kwargs):
        self.calls.append(("list_files", language))
        return [
            dict(doc)
            for (lang, _), doc in self.files.items()
            if lang == language
        ]

    def has_orphan_csv_files(self, language: str) -> bool:
        self.calls.append(("has_orphan_csv_files", language))
        return any(
            lang == language
            and (doc.get("filename") or "").lower().endswith(".csv")
            and not doc.get("topic_id")
            for (lang, _), doc in self.files.items()
        )

    def update_file_metadata(self, language: str, filename: str, metadata: dict):
        self.calls.append(("update_file_metadata", language, filename, metadata))
        doc = self.files.get((language, filename))
        if doc is None:
            return None
        doc.update(metadata)
        return dict(doc)

    def get_topic_csv_files(self, language: str, topic_id: str):
        self.calls.append(("get_topic_csv_files", language, topic_id))
        return [
            {"filename": doc["filename"], "data": doc["data"]}
            for (lang, _), doc in self.files.items()
            if lang == language and doc.get("topic_id") == topic_id and doc["filename"].endswith(".csv")
        ]


def _mounted_paths(app) -> set[str]:
    paths: set[str] = set()

    def collect(routes, prefix: str = "") -> None:
        for route in routes:
            path = getattr(route, "path", None)
            if isinstance(path, str):
                paths.add(f"{prefix}{path}")
                continue

            original_router = getattr(route, "original_router", None)
            include_context = getattr(route, "include_context", None)
            if original_router is not None and include_context is not None:
                collect(original_router.routes, f"{prefix}{include_context.prefix}")

    collect(app.routes)
    return paths


def test_jti_esg_topic_stores_use_dedicated_db_and_collections():
    from app.services import db_names
    from app.services.esg.topic_store import EsgTopicStore
    from app.services.jti.topic_store import JtiTopicStore

    assert JtiTopicStore.DB_NAME == db_names.JTI_DB_NAME
    assert JtiTopicStore.COLLECTION_NAME == "jti_topics"
    assert JtiTopicStore.CATEGORY_COLLECTION_NAME == "jti_categories"
    assert JtiTopicStore.NAMESPACE == "jti"

    assert EsgTopicStore.DB_NAME == db_names.ESG_DB_NAME
    assert EsgTopicStore.COLLECTION_NAME == "esg_topics"
    assert EsgTopicStore.CATEGORY_COLLECTION_NAME == "esg_categories"
    assert EsgTopicStore.NAMESPACE == "esg"


def test_jti_esg_topics_are_plain_single_language_docs():
    from app.routers.esg import topics_admin as esg_topics
    from app.routers.jti import topics_admin as jti_topics

    cases = [
        (esg_topics, "get_esg_topic_store"),
        (jti_topics, "get_jti_topic_store"),
    ]
    for module, getter_name in cases:
        store = FakePlainTopicStore()
        request = module.CreateTopicRequest(
            topic_id="faq/prp",
            labels="PRP",
            category_labels="FAQ",
            questions=["PRP 是什麼？"],
        )

        with patch.object(module, getter_name, side_effect=store.bind):
            created = module.create_topic("zh", request)

        assert created["labels"] == "PRP"
        assert created["category_labels"] == "FAQ"
        assert created["questions"] == ["PRP 是什麼？"]
        assert created["hidden_questions"] == []


def test_esg_first_empty_topic_read_imports_seed_csv_as_plain_topics(tmp_path, monkeypatch):
    from app.routers.esg import topics_admin

    esg_dir = tmp_path / "esg"
    esg_dir.mkdir()
    (esg_dir / "KIOSK_QA_中文.csv").write_text(
        "index,q,a\n"
        "1,【永續經營】,answer\n"
        "2,【環境】綠色營運,answer\n"
        "3,一般問題,answer\n",
        encoding="utf-8",
    )
    store = FakePlainTopicStore()
    knowledge_store = FakePlainKnowledgeStore()

    monkeypatch.setattr(topics_admin, "SEED_DATA_ROOT", tmp_path)
    with (
        patch.object(topics_admin, "get_esg_topic_store", side_effect=store.bind),
        patch.object(topics_admin, "get_esg_knowledge_store", return_value=knowledge_store),
    ):
        result = topics_admin.list_topics_all("zh")

    # 扁平一層：不依 CSV 的【分類】前綴拆層，所有 q 原文放進單一「常見問題」分類。
    category_labels = [category["label"] for category in result["categories"]]
    assert category_labels == ["常見問題"]

    topics = result["categories"][0]["topics"]
    assert len(topics) == 1
    topic = topics[0]
    assert topic["label"] == "常見問題"
    # 問題即 CSV 的 q 原文（含【分類】前綴），不做任何拆解/改寫。
    assert topic["questions"] == ["【永續經營】", "【環境】綠色營運", "一般問題"]
    assert isinstance(topic["questions"], list)
    assert knowledge_store.get_file("zh", "KIOSK_QA_中文.csv")["topic_id"] == "常見問題/常見問題"


def test_esg_seed_read_adopts_existing_orphan_kiosk_csv_when_topic_already_exists(tmp_path, monkeypatch):
    from app.routers.esg import topics_admin

    esg_dir = tmp_path / "esg"
    esg_dir.mkdir()
    (esg_dir / "KIOSK_QA_中文.csv").write_text(
        "index,q,a\n"
        "1,一般問題,answer\n",
        encoding="utf-8",
    )
    topic_store = FakePlainTopicStore()
    topic_store.upsert_topic(
        "常見問題/常見問題",
        {
            "labels": {"zh": "常見問題", "en": "FAQ"},
            "category_labels": {"zh": "常見問題", "en": "FAQ"},
            "questions": ["一般問題"],
            "hidden_questions": [],
            "hidden": False,
            "order": 0,
        },
    )
    knowledge_store = FakePlainKnowledgeStore()
    knowledge_store.insert_file(
        language="zh",
        filename="KIOSK_QA_中文.csv",
        data=b"index,q,a\n1,\xe4\xb8\x80\xe8\x88\xac\xe5\x95\x8f\xe9\xa1\x8c,answer\n",
        display_name="KIOSK_QA_中文.csv",
        content_type="text/csv",
        editable=True,
    )

    monkeypatch.setattr(topics_admin, "SEED_DATA_ROOT", tmp_path)
    with (
        patch.object(topics_admin, "get_esg_topic_store", side_effect=topic_store.bind),
        patch.object(topics_admin, "get_esg_knowledge_store", return_value=knowledge_store),
    ):
        topics_admin.list_topics_all("zh")

    assert knowledge_store.get_file("zh", "KIOSK_QA_中文.csv")["topic_id"] == "常見問題/常見問題"
    assert knowledge_store.get_topic_csv_files("zh", "常見問題/常見問題")[0]["filename"] == "KIOSK_QA_中文.csv"
    assert [call[0] for call in knowledge_store.calls].count("insert_file") == 1


def test_jti_topic_read_adopts_orphan_csvs_into_single_faq_topic():
    """JTI has no data/jti seed file — its Q&A ships as CSVs already in the
    knowledge store. Reading topics folds every untagged CSV into one
    "常見問題" topic so the 文件 view renders them as a single Q&A 整合 table."""
    from app.routers.jti import topics_admin

    store = FakePlainTopicStore()
    knowledge_store = FakePlainKnowledgeStore()
    for n in (1, 2):
        knowledge_store.insert_file(
            language="zh",
            filename=f"jti_{n:03d}.csv",
            data=f"q,a\nQ{n}?,A{n}\n".encode("utf-8"),
            display_name=f"jti_{n:03d}.csv",
            content_type="text/csv",
            editable=True,
        )

    with (
        patch.object(topics_admin, "get_jti_topic_store", side_effect=store.bind),
        patch.object(topics_admin, "get_jti_knowledge_store", return_value=knowledge_store),
    ):
        result = topics_admin.list_topics_all("zh")

    categories = result["categories"]
    assert [category["label"] for category in categories] == ["常見問題"]
    topics = categories[0]["topics"]
    assert len(topics) == 1
    assert topics[0]["label"] == "常見問題"
    assert topics[0]["questions"] == ["Q1?", "Q2?"]
    # Every CSV is now tagged to the single topic — none left orphaned.
    for n in (1, 2):
        assert knowledge_store.get_file("zh", f"jti_{n:03d}.csv")["topic_id"] == "常見問題/常見問題"
    assert len(knowledge_store.get_topic_csv_files("zh", "常見問題/常見問題")) == 2


def test_jti_topic_read_is_noop_when_no_csvs_present():
    from app.routers.jti import topics_admin

    store = FakePlainTopicStore()
    knowledge_store = FakePlainKnowledgeStore()

    with (
        patch.object(topics_admin, "get_jti_topic_store", side_effect=store.bind),
        patch.object(topics_admin, "get_jti_knowledge_store", return_value=knowledge_store),
    ):
        result = topics_admin.list_topics_all("zh")

    assert result == {"categories": []}
    assert [call for call in store.calls if call[0] == "upsert_topic"] == []


def test_jti_topic_read_skips_full_scan_when_no_orphan_csvs():
    """Steady state (every CSV already tagged): the cheap has_orphan_csv_files
    preflight must short-circuit so the read path never pulls the full file
    list — that scan was the dominant cost of this public endpoint."""
    from app.routers.jti import topics_admin

    store = FakePlainTopicStore()
    knowledge_store = FakePlainKnowledgeStore()
    # A CSV that is already adopted (has a topic_id) → not an orphan.
    knowledge_store.insert_file(
        language="zh",
        filename="jti_001.csv",
        data=b"q,a\nQ1?,A1\n",
        topic_id="faq/faq",
    )

    with (
        patch.object(topics_admin, "get_jti_topic_store", side_effect=store.bind),
        patch.object(topics_admin, "get_jti_knowledge_store", return_value=knowledge_store),
    ):
        topics_admin.list_topics_all("zh")

    call_names = [call[0] for call in knowledge_store.calls]
    assert "has_orphan_csv_files" in call_names
    assert "list_files" not in call_names


def test_main_mounts_jti_esg_topic_and_merged_csv_routes():
    app = get_test_app()
    paths = _mounted_paths(app)

    assert {
        "/api/jti/topics/{lang}",
        "/api/jti/topics/{lang}/all",
        "/api/jti-admin/topics/{language}/",
        "/api/jti-admin/topics/{language}/reorder",
        "/api/jti-admin/knowledge/topic-csv-merged",
        "/api/esg/topics/{lang}",
        "/api/esg/topics/{lang}/all",
        "/api/esg-admin/topics/{language}/",
        "/api/esg-admin/topics/{language}/reorder",
        "/api/esg-admin/knowledge/topic-csv-merged",
    } <= paths
