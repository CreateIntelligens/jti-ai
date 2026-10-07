import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import httpx

# Ensure app is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.services.embedding.errors import EmbeddingEncodingError
from app.services.embedding.service import EmbeddingService

REV = "914f7f89142e33e77833254d9c9b90c3cef7303b"


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

    @staticmethod
    def _extended_response(vectors, input_type="document", identity=None):
        identity = identity or (
            "gemma:google/embeddinggemma-2:768:float32:l2:"
            f"{input_type}:{REV}"
        )
        return {
            "vectors": vectors,
            "model": "google/embeddinggemma-2",
            "embedding_spec": {
                "identity": identity,
                "provider": "gemma",
                "model": "google/embeddinggemma-2",
                "dimensions": 768,
                "dtype": "float32",
                "normalized": True,
                "normalization": "l2",
                "input_semantics": input_type,
                "model_revision": REV,
                "service_revision": "1.0.0",
            },
            "attempts": [{"provider": "gemma", "status": "selected"}],
        }

    def test_remote_encode_returns_2d_ndarray(self):
        service = self._make_service()

        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"vectors": [[0.1] * 768]}

        class FakeClient:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def post(self_inner, url, json, headers):
                captured["url"] = url
                captured["payload"] = json
                captured["headers"] = headers
                return FakeResponse()

        with patch("httpx.Client", return_value=FakeClient()):
            result = service.encode("hello", input_type="query")

        self.assertEqual(result.shape, (1, 768))
        self.assertEqual(captured["url"], "http://embedding:8009")
        self.assertEqual(captured["payload"]["texts"], ["hello"])
        self.assertEqual(captured["payload"]["input_type"], "query")
        self.assertEqual(captured["headers"], {})

    def test_remote_encode_sends_bearer_token_and_validates_metadata(self):
        with patch.dict(
            os.environ,
            {
                "EMBEDDING_SERVICE_URL": (
                    "https://openvman.example.com/api/embedding"
                ),
                "EMBEDDING_SERVICE_TOKEN": "secret-token",
            },
        ):
            service = EmbeddingService()

        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return TestEmbeddingServiceRemote._extended_response(
                    [[0.1] * 768],
                    input_type="query",
                )

        class FakeClient:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def post(self_inner, url, json, headers):
                captured["url"] = url
                captured["headers"] = headers
                return FakeResponse()

        with patch("httpx.Client", return_value=FakeClient()):
            result = service.encode("hello", input_type="query")

        self.assertEqual(result.shape, (1, 768))
        self.assertEqual(
            captured["url"],
            "https://openvman.example.com/api/embedding",
        )
        self.assertEqual(
            captured["headers"],
            {"Authorization": "Bearer secret-token"},
        )

    def test_remote_encode_batch_chunks(self):
        service = self._make_service()

        post_calls = []

        class FakeResponse:
            def __init__(self, n):
                self._n = n

            def raise_for_status(self):
                pass

            def json(self):
                return {"vectors": [[0.1] * 768 for _ in range(self._n)]}

        class FakeClient:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def post(self_inner, url, json, headers):
                post_calls.append(len(json["texts"]))
                return FakeResponse(len(json["texts"]))

        texts = [f"t{i}" for i in range(130)]  # > 2 chunks of 64
        with patch("httpx.Client", return_value=FakeClient()):
            result = service.encode(texts)

        self.assertEqual(result.shape, (130, 768))
        self.assertEqual(post_calls, [64, 64, 2])

    def test_extended_batches_lock_the_selected_identity(self):
        service = self._make_service()
        payloads = []
        identity = (
            "gemma:google/embeddinggemma-2:768:float32:l2:document:" + REV
        )

        class FakeResponse:
            def __init__(self, count):
                self._count = count

            def raise_for_status(self):
                pass

            def json(self):
                return TestEmbeddingServiceRemote._extended_response(
                    [[0.1] * 768 for _ in range(self._count)],
                    identity=identity,
                )

        class FakeClient:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def post(self_inner, url, json, headers):
                payloads.append(json)
                return FakeResponse(len(json["texts"]))

        with patch("httpx.Client", return_value=FakeClient()):
            result = service.encode([f"text-{index}" for index in range(65)])

        self.assertEqual(result.shape, (65, 768))
        # 第一批就要帶 identity，否則服務會照它自己的 fallback 順序挑模型
        self.assertEqual(payloads[0]["identity"], identity)
        self.assertEqual(payloads[1]["identity"], identity)

    def test_incompatible_extended_metadata_raises(self):
        service = self._make_service()

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                data = TestEmbeddingServiceRemote._extended_response(
                    [[0.1] * 768]
                )
                data["embedding_spec"]["dimensions"] = 1024
                return data

        class FakeClient:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def post(self_inner, url, json, headers):
                return FakeResponse()

        with (
            patch("httpx.Client", return_value=FakeClient()),
            self.assertRaises(EmbeddingEncodingError),
        ):
            service.encode("hello")

    def test_remote_encode_http_error_raises(self):
        import httpx

        service = self._make_service()

        class FakeClient:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def post(self_inner, url, json, headers):
                raise httpx.ConnectError("refused")

        with (
            patch("httpx.Client", return_value=FakeClient()),
            self.assertRaises(EmbeddingEncodingError),
        ):
            service.encode("hello")


class TestEmbeddingServiceHealthCheck(unittest.TestCase):

    def setUp(self):
        EmbeddingService._instance = None

    def _make_service(self, env=None):
        merged = {"EMBEDDING_SERVICE_URL": "http://embedding:8009"}
        merged.update(env or {})
        with patch.dict(os.environ, merged):
            return EmbeddingService()

    def test_health_check_ok(self):
        service = self._make_service()

        class FakeResponse:
            status_code = 200

        with patch("httpx.get", return_value=FakeResponse()) as mock_get:
            self.assertTrue(service.health_check())
        self.assertEqual(
            mock_get.call_args.args[0], "http://embedding:8009/health"
        )
        self.assertEqual(mock_get.call_args.kwargs["headers"], {})

    def test_health_check_sends_bearer_token(self):
        service = self._make_service(
            {"EMBEDDING_SERVICE_TOKEN": "secret-token"}
        )

        class FakeResponse:
            status_code = 200

        with patch("httpx.get", return_value=FakeResponse()) as mock_get:
            self.assertTrue(service.health_check())
        self.assertEqual(
            mock_get.call_args.kwargs["headers"],
            {"Authorization": "Bearer secret-token"},
        )

    def test_health_check_non_200_is_unhealthy(self):
        service = self._make_service()

        class FakeResponse:
            status_code = 503

        with patch("httpx.get", return_value=FakeResponse()):
            self.assertFalse(service.health_check())

    def test_health_check_connection_error_is_unhealthy(self):
        import httpx

        service = self._make_service()

        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            self.assertFalse(service.health_check())


class TestEmbeddingRetryOnRateLimit(unittest.TestCase):
    """429/503 是暫時性的，單次放棄會讓整個 RAG 檢索回 0 命中。"""

    def setUp(self):
        EmbeddingService._instance = None

    @staticmethod
    def _response(status, json_body=None, headers=None):
        request = httpx.Request("POST", "http://embedding:8009")
        return httpx.Response(
            status,
            json=json_body if json_body is not None else {},
            headers=headers or {},
            request=request,
        )

    def _ok_body(self):
        identity = (
            "gemma:google/embeddinggemma-2:768:float32:l2:query:" + REV
        )
        return {
            "vectors": [[0.1] * 768],
            "model": "google/embeddinggemma-2",
            "embedding_spec": {
                "identity": identity,
                "dimensions": 768,
                "dtype": "float32",
                "model": "google/embeddinggemma-2",
                "model_revision": REV,
                "normalization": "l2",
                "normalized": True,
                "input_semantics": "query",
                "provider": "gemma",
                "service_revision": "1.0.0",
            },
            "attempts": [],
        }

    def _make_service(self):
        with patch.dict(os.environ,
                        {"EMBEDDING_SERVICE_URL": "http://embedding:8009"}):
            return EmbeddingService()

    def test_retries_429_then_succeeds(self):
        service = self._make_service()
        responses = [
            self._response(429),
            self._response(200, self._ok_body()),
        ]
        client = MagicMock()
        client.post.side_effect = responses
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)

        with patch("app.services.embedding.service.httpx.Client",
                   return_value=client), \
                patch("app.services.embedding.service.time.sleep") as sleep:
            result = service.encode("hi", input_type="query")

        self.assertEqual(client.post.call_count, 2)
        self.assertEqual(result.shape, (1, 768))
        sleep.assert_called_once()

    def test_gives_up_after_three_attempts(self):
        service = self._make_service()
        client = MagicMock()
        client.post.return_value = self._response(429)
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.services.embedding.service.httpx.Client", return_value=client),
            patch("app.services.embedding.service.time.sleep"),
            self.assertRaises(EmbeddingEncodingError) as ctx,
        ):
            service.encode("hi", input_type="query")

        self.assertEqual(client.post.call_count, 3)
        # 訊息要帶狀態碼，否則分不出「被限流」還是「服務掛了」
        self.assertIn("429", str(ctx.exception))

    def test_does_not_retry_client_error(self):
        """401 之類重試也不會變好，應該直接失敗。"""
        service = self._make_service()
        client = MagicMock()
        client.post.return_value = self._response(401)
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.services.embedding.service.httpx.Client", return_value=client),
            patch("app.services.embedding.service.time.sleep") as sleep,
            self.assertRaises(EmbeddingEncodingError),
        ):
            service.encode("hi", input_type="query")

        self.assertEqual(client.post.call_count, 1)
        sleep.assert_not_called()

    def test_respects_retry_after_header(self):
        service = self._make_service()
        client = MagicMock()
        client.post.side_effect = [
            self._response(429, headers={"Retry-After": "2"}),
            self._response(200, self._ok_body()),
        ]
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)

        with patch("app.services.embedding.service.httpx.Client",
                   return_value=client), \
                patch("app.services.embedding.service.time.sleep") as sleep:
            service.encode("hi", input_type="query")

        sleep.assert_called_once_with(2.0)


class TestEmbeddingIdentityAndTitles(unittest.TestCase):
    """換模型後查詢與文件向量必須出自同一個釘死的模型。"""

    def setUp(self):
        EmbeddingService._instance = None

    def _make_service(self, env=None):
        merged = {"EMBEDDING_SERVICE_URL": "http://embedding:8009"}
        merged.update(env or {})
        with patch.dict(os.environ, merged):
            return EmbeddingService()

    @staticmethod
    def _client(payloads, identity_for=None):
        def post(url, json, headers):
            payloads.append(json)
            input_type = json["input_type"]
            body = TestEmbeddingServiceRemote._extended_response(
                [[0.1] * 768 for _ in json["texts"]],
                input_type=input_type,
                identity=identity_for(input_type) if identity_for else None,
            )
            return httpx.Response(
                200,
                json=body,
                request=httpx.Request("POST", url),
            )

        client = MagicMock()
        client.post.side_effect = post
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        return client

    def test_query_and_document_pin_their_own_identity(self):
        service = self._make_service()
        payloads = []
        with patch("app.services.embedding.service.httpx.Client",
                   return_value=self._client(payloads)):
            service.encode("q", input_type="query")
            service.encode("d", input_type="document")

        self.assertEqual(
            payloads[0]["identity"],
            "gemma:google/embeddinggemma-2:768:float32:l2:query:" + REV,
        )
        self.assertEqual(
            payloads[1]["identity"],
            "gemma:google/embeddinggemma-2:768:float32:l2:document:" + REV,
        )

    def test_search_query_identity(self):
        """jtai 檢索用 search_query 語意；服務端依此套 search result 前綴。"""
        service = self._make_service()
        self.assertEqual(
            service._identity("search_query"),
            "gemma:google/embeddinggemma-2:768:float32:l2:search_query:" + REV,
        )

    def test_response_from_other_model_is_rejected(self):
        service = self._make_service()
        with (
            patch(
                "app.services.embedding.service.httpx.Client",
                return_value=self._client(
                    [],
                    identity_for=lambda t: (
                        f"gemma:google/embeddinggemma-2:768:float32:l2:{t}:other"
                    ),
                ),
            ),
            self.assertRaises(EmbeddingEncodingError),
        ):
            service.encode("q", input_type="query")

    def test_empty_provider_env_still_pins_default_model(self):
        """compose 沒設變數時傳進來的是空字串，不能因此失去 identity。"""
        service = self._make_service(
            {"EMBEDDING_PROVIDER": "", "EMBEDDING_MODEL_REVISION": ""}
        )
        self.assertEqual(
            service._identity("query"),
            "gemma:google/embeddinggemma-2:768:float32:l2:query:" + REV,
        )

    def test_other_model_without_provider_sends_no_identity(self):
        """自架 bge 的部署沒設 provider 時維持舊行為，不能被套上 gemma 的 identity。"""
        service = self._make_service({
            "EMBEDDING_EXPECTED_MODEL": "BAAI/bge-m3",
            "EMBEDDING_EXPECTED_DIMENSION": "1024",
            "EMBEDDING_PROVIDER": "",
        })
        self.assertIsNone(service._identity("query"))

    def test_other_model_with_provider_is_pinned(self):
        service = self._make_service({
            "EMBEDDING_EXPECTED_MODEL": "BAAI/bge-m3",
            "EMBEDDING_EXPECTED_DIMENSION": "1024",
            "EMBEDDING_PROVIDER": "bge",
            "EMBEDDING_MODEL_REVISION": "abc",
        })
        self.assertEqual(
            service._identity("document"),
            "bge:BAAI/bge-m3:1024:float32:l2:document:abc",
        )

    def test_document_titles_follow_batches(self):
        service = self._make_service()
        payloads = []
        texts = [f"t{i}" for i in range(70)]
        titles = [f"title-{i}" for i in range(70)]
        with patch("app.services.embedding.service.httpx.Client",
                   return_value=self._client(payloads)):
            service.encode(texts, titles=titles)

        self.assertEqual(payloads[0]["titles"], titles[:64])
        self.assertEqual(payloads[1]["titles"], titles[64:])

    def test_query_never_sends_titles(self):
        service = self._make_service()
        payloads = []
        with patch("app.services.embedding.service.httpx.Client",
                   return_value=self._client(payloads)):
            service.encode("q", input_type="query", titles=["ignored"])

        self.assertNotIn("titles", payloads[0])

    def test_titles_length_mismatch_raises(self):
        service = self._make_service()
        with self.assertRaises(ValueError):
            service.encode(["a", "b"], titles=["only-one"])


if __name__ == '__main__':
    unittest.main()
