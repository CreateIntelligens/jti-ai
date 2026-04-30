from unittest.mock import patch

from tests.support.app_test_support import install_app_import_mocks

install_app_import_mocks()

from app.routers.hciot import topics_admin


class FakeStore:
    def __init__(self):
        self.topics: dict[str, dict] = {}
        self.categories: list[dict] = []

    def get_topic(self, topic_id: str):
        topic = self.topics.get(topic_id)
        return None if topic is None else {"topic_id": topic_id, **topic}

    def upsert_topic(self, topic_id: str, data: dict) -> None:
        self.topics[topic_id] = dict(data)

    def update_topic(self, topic_id: str, data: dict) -> bool:
        if topic_id not in self.topics:
            return False
        self.topics[topic_id].update(data)
        return True

    def list_categories(self):
        return self.categories


def test_create_topic_preserves_blank_label_fields_without_auto_translation():
    store = FakeStore()
    request = topics_admin.CreateTopicRequest(
        topic_id="ortho/prp",
        labels=topics_admin.BilingualLabels(zh="PRP", en=""),
        category_labels=topics_admin.BilingualLabels(zh="骨科", en=""),
    )

    with patch.object(topics_admin, "get_hciot_topic_store", return_value=store):
        result = topics_admin.create_topic(request)

    assert result["labels"] == {"zh": "PRP", "en": ""}
    assert result["category_labels"] == {"zh": "骨科", "en": ""}


def test_update_topic_preserves_blank_label_fields_without_auto_translation():
    store = FakeStore()
    store.upsert_topic(
        "ortho/prp",
        {
            "labels": {"zh": "PRP", "en": "PRP Therapy"},
            "category_labels": {"zh": "骨科", "en": "Orthopedics"},
            "questions": {"zh": [], "en": []},
        },
    )
    request = topics_admin.UpdateTopicRequest(
        labels=topics_admin.BilingualLabels(zh="PRP", en=""),
        category_labels=topics_admin.BilingualLabels(zh="骨科", en=""),
    )

    with patch.object(topics_admin, "get_hciot_topic_store", return_value=store):
        result = topics_admin.update_topic("ortho/prp", request)

    assert result["labels"] == {"zh": "PRP", "en": ""}
    assert result["category_labels"] == {"zh": "骨科", "en": ""}


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

    with patch.object(topics_admin, "get_hciot_topic_store", return_value=store):
        result = topics_admin.list_topics()

    assert [category["id"] for category in result["categories"]] == ["faq", "ortho"]
    assert [topic["id"] for topic in result["categories"][1]["topics"]] == ["ortho/faq", "ortho/prp"]
