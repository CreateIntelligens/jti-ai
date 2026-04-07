import unittest
from unittest.mock import MagicMock

from app.services.jti.cleanup_knowledge_core_markers import cleanup_knowledge_core_markers


class TestJtiCleanupKnowledgeCoreMarkers(unittest.TestCase):
    def test_dry_run_counts_only_docs_with_core_markers(self):
        store = MagicMock()
        store.collection.find.return_value = [
            {
                "filename": "guide.csv",
                "language": "zh",
                "namespace": "jti",
                "data": b"prefix [CORE: important] suffix",
            },
            {
                "filename": "plain.csv",
                "language": "zh",
                "namespace": "jti",
                "data": b"plain content",
            },
            {
                "filename": "manual.pdf",
                "language": "zh",
                "namespace": "jti",
                "data": b"%PDF-1.4",
            },
        ]

        summary = cleanup_knowledge_core_markers(store=store)

        self.assertEqual(summary, {"scanned": 3, "updated": 1, "skipped": 2})
        store.update_file_content.assert_not_called()

    def test_apply_updates_matching_docs(self):
        store = MagicMock()
        store.collection.find.return_value = [
            {
                "filename": "guide.csv",
                "language": "zh",
                "namespace": "jti",
                "data": b"prefix [CORE: important] suffix",
            }
        ]

        summary = cleanup_knowledge_core_markers(dry_run=False, store=store)

        self.assertEqual(summary, {"scanned": 1, "updated": 1, "skipped": 0})
        store.update_file_content.assert_called_once_with(
            "zh",
            "guide.csv",
            b"prefix important suffix",
            namespace="jti",
        )


if __name__ == "__main__":
    unittest.main()
