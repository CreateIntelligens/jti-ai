import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from tests.app_main_test_support import install_app_import_mocks

install_app_import_mocks()

from app.routers.knowledge_utils import delete_from_gemini, sync_to_gemini


class TestKnowledgeSync(unittest.TestCase):
    @patch("app.routers.knowledge_utils._get_or_create_manager")
    def test_delete_from_gemini_deletes_all_matching_documents(self, mock_get_manager):
        mgr = MagicMock()
        mgr.list_files.return_value = [
            SimpleNamespace(display_name="faq.csv", name="documents/1"),
            SimpleNamespace(display_name="other.csv", name="documents/2"),
            SimpleNamespace(display_name="faq.csv", name="documents/3"),
        ]
        mock_get_manager.return_value = mgr

        deleted_count = delete_from_gemini("fileSearchStores/test", "faq.csv")

        self.assertEqual(deleted_count, 2)
        self.assertEqual(
            mgr.delete_file.call_args_list,
            [call("documents/1"), call("documents/3")],
        )

    @patch("app.routers.knowledge_utils._get_or_create_manager")
    def test_sync_to_gemini_cleans_all_duplicates_before_upload(self, mock_get_manager):
        mgr = MagicMock()
        mgr.list_files.return_value = [
            SimpleNamespace(display_name="faq.csv", name="documents/1"),
            SimpleNamespace(display_name="faq.csv", name="documents/2"),
        ]
        mock_get_manager.return_value = mgr

        synced = sync_to_gemini("fileSearchStores/test", "faq.csv", b"hello")

        self.assertTrue(synced)
        self.assertEqual(
            mgr.delete_file.call_args_list,
            [call("documents/1"), call("documents/2")],
        )
        mgr.upload_file.assert_called_once()
        args = mgr.upload_file.call_args.args
        self.assertEqual(args[0], "fileSearchStores/test")
        self.assertEqual(args[2], "faq.csv")


if __name__ == "__main__":
    unittest.main()
