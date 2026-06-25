import os
import sys
import unittest
from unittest.mock import patch

# Ensure app is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.services.embedding.errors import EmbeddingEncodingError
from app.services.embedding.service import EmbeddingService


class TestEmbeddingServiceRequiresUrl(unittest.TestCase):

    def setUp(self):
        EmbeddingService._instance = None

    def test_missing_url_raises(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMBEDDING_SERVICE_URL", None)
            with self.assertRaises(EmbeddingEncodingError):
                EmbeddingService()


class TestEmbeddingServiceRemote(unittest.TestCase):

    def setUp(self):
        EmbeddingService._instance = None

    def _make_service(self):
        with patch.dict(os.environ,
                        {"EMBEDDING_SERVICE_URL": "http://embedding:8009"}):
            return EmbeddingService()

    def test_remote_encode_returns_2d_ndarray(self):
        service = self._make_service()

        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"vectors": [[0.1] * 1024]}

        class FakeClient:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def post(self_inner, url, json):
                captured["url"] = url
                captured["payload"] = json
                return FakeResponse()

        with patch("httpx.Client", return_value=FakeClient()):
            result = service.encode("hello", input_type="query")

        self.assertEqual(result.shape, (1, 1024))
        self.assertEqual(captured["url"], "http://embedding:8009/embed")
        self.assertEqual(captured["payload"]["texts"], ["hello"])
        self.assertEqual(captured["payload"]["input_type"], "query")

    def test_remote_encode_batch_chunks(self):
        service = self._make_service()

        post_calls = []

        class FakeResponse:
            def __init__(self, n):
                self._n = n

            def raise_for_status(self):
                pass

            def json(self):
                return {"vectors": [[0.1] * 1024 for _ in range(self._n)]}

        class FakeClient:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def post(self_inner, url, json):
                post_calls.append(len(json["texts"]))
                return FakeResponse(len(json["texts"]))

        texts = [f"t{i}" for i in range(130)]  # > 2 chunks of 64
        with patch("httpx.Client", return_value=FakeClient()):
            result = service.encode(texts)

        self.assertEqual(result.shape, (130, 1024))
        self.assertEqual(post_calls, [64, 64, 2])

    def test_remote_encode_http_error_raises(self):
        import httpx

        service = self._make_service()

        class FakeClient:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def post(self_inner, url, json):
                raise httpx.ConnectError("refused")

        with patch("httpx.Client", return_value=FakeClient()):
            with self.assertRaises(EmbeddingEncodingError):
                service.encode("hello")


if __name__ == '__main__':
    unittest.main()
