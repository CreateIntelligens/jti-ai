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
        return root.categories_by_language.get(self.language, root.categories)


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
        result = topics_admin.create_topic(request, language="zh")

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
        result = topics_admin.update_topic("ortho/prp", request, language="zh")

    assert result["labels"] == {"zh": "PRP 治療", "en": ""}
    assert result["category_labels"] == {"zh": "骨科部", "en": ""}


def test_public_topics_places_common_questions_first():
    store = FakeStore()
    store.categories = [
        {
            "id": "ortho",
            "labels": {"zh": "骨科", "en": "Orthopedics"},
            "topics": [
                {
                    "id": "ortho/prp",
                    "labels": {"zh": "PRP 治療", "en": "PRP Therapy"},
                    "questions": {"zh": [], "en": []},
                },
                {
                    "id": "ortho/faq",
                    "labels": {"zh": "常見問題", "en": "FAQ"},
                    "questions": {"zh": [], "en": []},
                },
            ],
        },
        {
            "id": "faq",
            "labels": {"zh": "常見問題", "en": "FAQ"},
            "topics": [],
        },
    ]

    with patch_topic_store(store):
        result = topics_admin.list_topics_slim("zh")

    assert [category["id"] for category in result["categories"]] == ["faq", "ortho"]
    assert [topic["id"] for topic in result["categories"][1]["topics"]] == ["ortho/faq", "ortho/prp"]


def test_public_topics_query_route_is_not_registered():
    routes = [
        (route.path, method)
        for route in topics_admin.public_router.routes
        for method in getattr(route, "methods", set())
    ]

    assert ("/topics", "GET") not in routes
    assert ("/topics/{lang}", "GET") in routes


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
        result = topics_admin.create_topic(request, language="en")

    # The English partition gets its own document; the Chinese one is untouched.
    assert result["labels"] == {"zh": "", "en": "Early Intervention"}
    assert store.bind("zh").get_topic("faq/early-intervention")["labels"]["zh"] == "兒童早療"
    assert store.bind("en").get_topic("faq/early-intervention")["category_labels"]["en"] == "FAQ"
