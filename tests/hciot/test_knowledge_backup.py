import json

from app.services.hciot.knowledge_backup import backup_hciot_knowledge_files


class FakeKnowledgeStore:
    def __init__(self):
        self.files = {
            "zh": [
                {
                    "filename": "faq.csv",
                    "display_name": "FAQ.csv",
                    "content_type": "text/csv",
                    "size": 12,
                    "editable": True,
                    "topic_id": "cat/topic",
                    "category_label": "Cat",
                    "topic_label": "Topic",
                },
                {
                    "filename": "missing.csv",
                    "display_name": "Missing.csv",
                    "content_type": "text/csv",
                },
            ],
            "en": [
                {
                    "filename": "guide.xlsx",
                    "display_name": "Guide.xlsx",
                    "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "size": 9,
                    "editable": True,
                }
            ],
        }
        self.payloads = {
            ("zh", "faq.csv"): {"data": b"q,a\nhi,ok\n", **self.files["zh"][0]},
            ("zh", "missing.csv"): None,
            ("en", "guide.xlsx"): {"data": b"xlsx-data", **self.files["en"][0]},
        }

    def list_files(self, language: str):
        return list(self.files.get(language, []))

    def get_file(self, language: str, filename: str):
        return self.payloads[(language, filename)]


def test_backup_hciot_knowledge_files_writes_files_and_manifest(tmp_path):
    result = backup_hciot_knowledge_files(store=FakeKnowledgeStore(), output_dir=tmp_path)

    assert result == {"total": 3, "written": 2, "skipped": 1, "failed": 0}
    assert (tmp_path / "zh" / "files" / "faq.csv").read_bytes() == b"q,a\nhi,ok\n"
    assert (tmp_path / "en" / "files" / "guide.xlsx").read_bytes() == b"xlsx-data"

    zh_manifest = json.loads((tmp_path / "zh" / "manifest.json").read_text())
    assert zh_manifest["language"] == "zh"
    assert zh_manifest["files"] == [
        {
            "filename": "faq.csv",
            "display_name": "FAQ.csv",
            "content_type": "text/csv",
            "size": 12,
            "editable": True,
            "topic_id": "cat/topic",
            "category_label": "Cat",
            "topic_label": "Topic",
            "backup_path": "files/faq.csv",
        }
    ]


def test_backup_hciot_knowledge_files_skips_unchanged_files(tmp_path):
    store = FakeKnowledgeStore()

    first = backup_hciot_knowledge_files(store=store, output_dir=tmp_path)
    second = backup_hciot_knowledge_files(store=store, output_dir=tmp_path)

    assert first == {"total": 3, "written": 2, "skipped": 1, "failed": 0}
    assert second == {"total": 3, "written": 0, "skipped": 3, "failed": 0}
