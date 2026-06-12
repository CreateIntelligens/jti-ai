from unittest.mock import patch

from tests.support.app_test_support import install_app_import_mocks

install_app_import_mocks()

from app.routers.hciot import topics_admin


class FakeStore:
    def __init__(self, language: str = "zh", root: "FakeStore | None" = None):
        self.language = language
        if root is not None:
            self._root = root
            return
        self._root = self
        self.topics: dict[tuple[str, str], dict] = {}
        self.categories: list[dict] = []
        self.categories_by_language: dict[str, list[dict]] = {}
        self.category_meta_by_language: dict[str, dict[str, dict]] = {}
        self.calls: list[tuple] = []

    def bind(self, language: str = "zh"):
        return FakeStore(language, self._root)

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
        categories = root.categories_by_language.get(self.language, root.categories)
        # Mirror HciotTopicStore: topics within a category arrive sorted by `order`.
        return [
            {**cat, "topics": sorted(cat.get("topics", []), key=lambda t: t.get("order", 0))}
            for cat in categories
        ]

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
            if root.topics.pop((self.language, topic_id), None) is not None:
                deleted += 1
        return deleted

    def set_category_hidden(self, category_id: str, hidden: bool) -> bool:
        root = self._root
        root.calls.append(("set_category_hidden", category_id, hidden, self.language))
        root.category_meta_by_language.setdefault(self.language, {}).setdefault(category_id, {})["hidden"] = hidden
        return True


def patch_topic_store(store: FakeStore):
    return patch.object(topics_admin, "get_hciot_topic_store", side_effect=store.bind)


def test_create_topic_stores_single_language_label_in_its_partition():
    store = FakeStore()
    request = topics_admin.CreateTopicRequest(
        topic_id="ortho/prp",
        labels="PRP",
        category_labels="骨科",
    )

    with patch_topic_store(store):
        result = topics_admin.create_topic("zh", request)

    # Single-language input is stored into the doc-level bilingual dict;
    # the other language slot stays blank.
    assert result["labels"] == {"zh": "PRP", "en": ""}
    assert result["category_labels"] == {"zh": "骨科", "en": ""}


def test_update_topic_writes_single_language_label_into_partition():
    store = FakeStore()
    store.bind("zh").upsert_topic(
        "ortho/prp",
        {
            "labels": {"zh": "PRP", "en": ""},
            "category_labels": {"zh": "骨科", "en": ""},
            "questions": {"zh": [], "en": []},
        },
    )
    request = topics_admin.UpdateTopicRequest(
        labels="PRP 治療",
        category_labels="骨科部",
    )

    with patch_topic_store(store):
        result = topics_admin.update_topic("zh", "ortho/prp", request)

    assert result["labels"] == {"zh": "PRP 治療", "en": ""}
    assert result["category_labels"] == {"zh": "骨科部", "en": ""}


def test_public_topics_are_ordered_by_stored_order_field():
    store = FakeStore()
    # Topics carry explicit `order`; categories inherit the smallest order
    # among their topics. "faq" (order 0) therefore sorts before "ortho".
    store.categories = [
        {
            "id": "ortho",
            "labels": {"zh": "骨科", "en": "Orthopedics"},
            "topics": [
                {
                    "id": "ortho/prp",
                    "labels": {"zh": "PRP 治療", "en": "PRP Therapy"},
                    "questions": {"zh": [], "en": []},
                    "order": 2,
                },
                {
                    "id": "ortho/knee",
                    "labels": {"zh": "膝關節", "en": "Knee"},
                    "questions": {"zh": [], "en": []},
                    "order": 1,
                },
            ],
        },
        {
            "id": "faq",
            "labels": {"zh": "常見問題", "en": "FAQ"},
            "topics": [
                {
                    "id": "faq/general",
                    "labels": {"zh": "一般問題", "en": "General"},
                    "questions": {"zh": [], "en": []},
                    "order": 0,
                },
            ],
        },
    ]

    with patch_topic_store(store):
        result = topics_admin.list_topics_slim("zh")

    # Category order: faq (min order 0) before ortho (min order 1).
    assert [category["id"] for category in result["categories"]] == ["faq", "ortho"]
    # Within ortho: knee (order 1) before prp (order 2).
    assert [topic["id"] for topic in result["categories"][1]["topics"]] == ["ortho/knee", "ortho/prp"]


def test_public_topics_query_route_is_not_registered():
    routes = [
        (route.path, method)
        for route in topics_admin.public_router.routes
        for method in getattr(route, "methods", set())
    ]

    assert ("/topics", "GET") not in routes
    assert ("/topics/{lang}", "GET") in routes
    assert ("/topics/{lang}/all", "GET") in routes


def test_localized_public_topics_return_slim_single_language_shape():
    store = FakeStore()
    store.categories = [
        {
            "id": "ortho",
            "labels": {"zh": "骨科", "en": "Orthopedics"},
            "topics": [
                {
                    "id": "ortho/prp",
                    "topic_id": "ortho/prp",
                    "labels": {"zh": "PRP 治療", "en": "PRP Therapy"},
                    "category_labels": {"zh": "骨科", "en": "Orthopedics"},
                    "order": 2,
                    "questions": {"zh": ["什麼是 PRP？"], "en": ["What is PRP?"]},
                    "updated_at": "internal",
                },
                {
                    "id": "ortho/faq",
                    "topic_id": "ortho/faq",
                    "labels": {"zh": "常見問題", "en": "FAQ"},
                    "category_labels": {"zh": "骨科", "en": "Orthopedics"},
                    "order": 1,
                    "questions": {"zh": ["常見問題"], "en": ["FAQ"]},
                },
            ],
        },
    ]

    with patch_topic_store(store):
        zh_result = topics_admin.list_topics_slim("zh")
        en_result = topics_admin.list_topics_slim("en")

    assert zh_result == {
        "categories": [
            {
                "id": "ortho",
                "label": "骨科",
                "order": 1,
                "topics": [
                    {
                        "id": "ortho/faq",
                        "label": "常見問題",
                        "order": 1,
                        "questions": ["常見問題"],
                    },
                    {
                        "id": "ortho/prp",
                        "label": "PRP 治療",
                        "order": 2,
                        "questions": ["什麼是 PRP？"],
                    },
                ],
            },
        ],
    }
    assert en_result["categories"][0]["label"] == "Orthopedics"
    assert en_result["categories"][0]["topics"][0] == {
        "id": "ortho/faq",
        "label": "FAQ",
        "order": 1,
        "questions": ["FAQ"],
    }


def test_localized_public_topics_read_separate_language_partitions():
    store = FakeStore()
    store.categories_by_language = {
        "zh": [
            {
                "id": "常見問題",
                "labels": {"zh": "常見問題", "en": "中文佔位"},
                "topics": [
                    {
                        "id": "常見問題/兒童早療",
                        "labels": {"zh": "兒童早療", "en": "中文佔位"},
                        "questions": {"zh": ["中文題"], "en": []},
                    },
                ],
            },
        ],
        "en": [
            {
                "id": "faq",
                "labels": {"zh": "FAQ", "en": "FAQ"},
                "topics": [
                    {
                        "id": "faq/early-intervention",
                        "labels": {"zh": "Early Intervention", "en": "Early Intervention"},
                        "questions": {"zh": [], "en": ["English question"]},
                    },
                ],
            },
        ],
    }

    with patch_topic_store(store):
        zh_result = topics_admin.list_topics_slim("zh")
        en_result = topics_admin.list_topics_slim("en")

    assert zh_result["categories"][0]["id"] == "常見問題"
    assert en_result["categories"][0]["id"] == "faq"
    assert en_result["categories"][0]["topics"][0]["questions"] == ["English question"]
    assert ("list_categories", "zh") in store.calls
    assert ("list_categories", "en") in store.calls


def test_create_english_topic_does_not_conflict_with_existing_chinese_topic():
    store = FakeStore()
    store.bind("zh").upsert_topic(
        "faq/early-intervention",
        {
            "labels": {"zh": "兒童早療", "en": ""},
            "category_labels": {"zh": "常見問題", "en": ""},
            "questions": {"zh": ["中文題"], "en": []},
        },
    )
    request = topics_admin.CreateTopicRequest(
        topic_id="faq/early-intervention",
        labels="Early Intervention",
        category_labels="FAQ",
    )

    with patch_topic_store(store):
        result = topics_admin.create_topic("en", request)

    # The English partition gets its own document; the Chinese one is untouched.
    assert result["labels"] == {"zh": "", "en": "Early Intervention"}
    assert store.bind("zh").get_topic("faq/early-intervention")["labels"]["zh"] == "兒童早療"
    assert store.bind("en").get_topic("faq/early-intervention")["category_labels"]["en"] == "FAQ"


def test_update_topic_saves_hidden_questions():
    store = FakeStore()
    store.bind("zh").upsert_topic(
        "ortho/prp",
        {
            "labels": {"zh": "PRP 治療", "en": ""},
            "category_labels": {"zh": "骨科", "en": ""},
            "questions": {"zh": ["Q1", "Q2"], "en": []},
            "hidden_questions": {"zh": [], "en": []},
        },
    )
    request = topics_admin.UpdateTopicRequest(
        hidden_questions=["Q2"],
    )

    with patch_topic_store(store):
        result = topics_admin.update_topic("zh", "ortho/prp", request)

    assert result["hidden_questions"] == {"zh": ["Q2"], "en": []}


def test_list_topics_slim_filters_hidden_questions_for_public_users():
    store = FakeStore()
    store.categories = [
        {
            "id": "ortho",
            "labels": {"zh": "骨科", "en": "Orthopedics"},
            "topics": [
                {
                    "id": "ortho/prp",
                    "topic_id": "ortho/prp",
                    "labels": {"zh": "PRP 治療", "en": "PRP Therapy"},
                    "category_labels": {"zh": "骨科", "en": "Orthopedics"},
                    "order": 1,
                    "questions": {"zh": ["Q1", "Q2", "Q3"], "en": []},
                    "hidden_questions": {"zh": ["Q2"], "en": []},
                },
            ],
        },
    ]

    with patch_topic_store(store):
        result = topics_admin.list_topics_slim("zh")

    topic = result["categories"][0]["topics"][0]
    assert topic["questions"] == ["Q1", "Q3"]
    assert "hidden_questions" not in topic


def test_list_topics_slim_removes_topics_and_categories_without_visible_questions():
    store = FakeStore()
    store.categories = [
        {
            "id": "ortho",
            "labels": {"zh": "骨科", "en": "Orthopedics"},
            "topics": [
                {
                    "id": "ortho/prp",
                    "topic_id": "ortho/prp",
                    "labels": {"zh": "PRP 治療", "en": "PRP Therapy"},
                    "category_labels": {"zh": "骨科", "en": "Orthopedics"},
                    "order": 1,
                    "questions": {"zh": ["Q1", "Q2"], "en": []},
                    "hidden_questions": {"zh": ["Q1", "Q2"], "en": []},
                },
                {
                    "id": "ortho/faq",
                    "topic_id": "ortho/faq",
                    "labels": {"zh": "常見問題", "en": "FAQ"},
                    "category_labels": {"zh": "骨科", "en": "Orthopedics"},
                    "order": 2,
                    "questions": {"zh": ["Q3"], "en": []},
                    "hidden_questions": {"zh": [], "en": []},
                },
            ],
        },
        {
            "id": "rehab",
            "labels": {"zh": "復健科", "en": "Rehab"},
            "topics": [
                {
                    "id": "rehab/only-hidden",
                    "topic_id": "rehab/only-hidden",
                    "labels": {"zh": "全部隱藏", "en": "Hidden"},
                    "category_labels": {"zh": "復健科", "en": "Rehab"},
                    "order": 3,
                    "questions": {"zh": ["Q4"], "en": []},
                    "hidden_questions": {"zh": ["Q4"], "en": []},
                },
            ],
        },
    ]

    with patch_topic_store(store):
        result = topics_admin.list_topics_slim("zh")

    assert [category["id"] for category in result["categories"]] == ["ortho"]
    assert [topic["id"] for topic in result["categories"][0]["topics"]] == ["ortho/faq"]


def test_list_topics_all_retains_hidden_questions():
    store = FakeStore()
    store.categories = [
        {
            "id": "ortho",
            "labels": {"zh": "骨科", "en": "Orthopedics"},
            "topics": [
                {
                    "id": "ortho/prp",
                    "topic_id": "ortho/prp",
                    "labels": {"zh": "PRP 治療", "en": "PRP Therapy"},
                    "category_labels": {"zh": "骨科", "en": "Orthopedics"},
                    "order": 1,
                    "questions": {"zh": ["Q1", "Q2", "Q3"], "en": []},
                    "hidden_questions": {"zh": ["Q2"], "en": []},
                },
            ],
        },
    ]

    with patch_topic_store(store):
        result = topics_admin.list_topics_all("zh")

    topic = result["categories"][0]["topics"][0]
    assert topic["questions"] == ["Q1", "Q2", "Q3"]
    assert topic["hidden_questions"] == ["Q2"]


def test_update_topic_saves_topic_hidden_flag():
    store = FakeStore()
    store.bind("zh").upsert_topic(
        "ortho/prp",
        {
            "labels": {"zh": "PRP 治療", "en": ""},
            "category_labels": {"zh": "骨科", "en": ""},
            "questions": {"zh": ["Q1"], "en": []},
            "hidden_questions": {"zh": [], "en": []},
            "hidden": False,
        },
    )
    request = topics_admin.UpdateTopicRequest(hidden=True)

    with patch_topic_store(store):
        result = topics_admin.update_topic("zh", "ortho/prp", request)

    assert result["hidden"] is True


def test_public_topics_filter_topic_hidden_flag_but_admin_retains_it():
    store = FakeStore()
    store.categories = [
        {
            "id": "ortho",
            "labels": {"zh": "骨科", "en": "Orthopedics"},
            "topics": [
                {
                    "id": "ortho/prp",
                    "topic_id": "ortho/prp",
                    "labels": {"zh": "PRP 治療", "en": "PRP Therapy"},
                    "category_labels": {"zh": "骨科", "en": "Orthopedics"},
                    "order": 1,
                    "questions": {"zh": ["Q1"], "en": []},
                    "hidden_questions": {"zh": [], "en": []},
                    "hidden": True,
                },
                {
                    "id": "ortho/faq",
                    "topic_id": "ortho/faq",
                    "labels": {"zh": "常見問題", "en": "FAQ"},
                    "category_labels": {"zh": "骨科", "en": "Orthopedics"},
                    "order": 2,
                    "questions": {"zh": ["Q2"], "en": []},
                    "hidden_questions": {"zh": [], "en": []},
                },
            ],
        },
    ]

    with patch_topic_store(store):
        public_result = topics_admin.list_topics_slim("zh")
        admin_result = topics_admin.list_topics_all("zh")

    assert [topic["id"] for topic in public_result["categories"][0]["topics"]] == ["ortho/faq"]
    admin_topics = admin_result["categories"][0]["topics"]
    assert [topic["id"] for topic in admin_topics] == ["ortho/prp", "ortho/faq"]
    assert admin_topics[0]["hidden"] is True
    assert admin_topics[1]["hidden"] is False


def test_public_topics_filter_category_meta_hidden_but_admin_retains_it():
    store = FakeStore()
    store.category_meta_by_language = {
        "zh": {
            "ortho": {"hidden": True},
        },
    }
    store.categories = [
        {
            "id": "ortho",
            "labels": {"zh": "骨科", "en": "Orthopedics"},
            "topics": [
                {
                    "id": "ortho/prp",
                    "topic_id": "ortho/prp",
                    "labels": {"zh": "PRP 治療", "en": "PRP Therapy"},
                    "category_labels": {"zh": "骨科", "en": "Orthopedics"},
                    "order": 1,
                    "questions": {"zh": ["Q1"], "en": []},
                    "hidden_questions": {"zh": [], "en": []},
                },
            ],
        },
        {
            "id": "faq",
            "labels": {"zh": "常見問題", "en": "FAQ"},
            "topics": [
                {
                    "id": "faq/general",
                    "topic_id": "faq/general",
                    "labels": {"zh": "一般", "en": "General"},
                    "category_labels": {"zh": "常見問題", "en": "FAQ"},
                    "order": 2,
                    "questions": {"zh": ["Q2"], "en": []},
                    "hidden_questions": {"zh": [], "en": []},
                },
            ],
        },
    ]

    with patch_topic_store(store):
        public_result = topics_admin.list_topics_slim("zh")
        admin_result = topics_admin.list_topics_all("zh")

    assert [category["id"] for category in public_result["categories"]] == ["faq"]
    assert [category["id"] for category in admin_result["categories"]] == ["ortho", "faq"]
    assert admin_result["categories"][0]["hidden"] is True
    assert admin_result["categories"][1]["hidden"] is False


def test_update_category_visibility_writes_category_meta():
    store = FakeStore()
    request = topics_admin.UpdateCategoryVisibilityRequest(hidden=True)

    with patch_topic_store(store):
        result = topics_admin.update_category_visibility("zh", "ortho", request)

    assert result == {"category_id": "ortho", "hidden": True}
    assert ("set_category_hidden", "ortho", True, "zh") in store.calls


def test_delete_topics_batch_delegates_to_store_in_one_call():
    store = FakeStore()
    store.bind("zh").upsert_topic("faq/a", {"labels": {"zh": "A", "en": ""}})
    store.bind("zh").upsert_topic("faq/b", {"labels": {"zh": "B", "en": ""}})

    request = topics_admin.DeleteTopicsRequest(topic_ids=["faq/a", "faq/b"])
    with patch_topic_store(store):
        result = topics_admin.delete_topics_batch("zh", request)

    assert result == {"deleted": 2}
    assert ("delete_topics", ["faq/a", "faq/b"], "zh") in store.calls
