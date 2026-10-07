"""docker/embedding/app.py：自架 EmbeddingGemma 2 必須與 openVman 算出同一個向量空間。"""
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from fastapi import HTTPException

_APP_PATH = Path(__file__).resolve().parents[2] / "docker" / "embedding" / "app.py"
_spec = importlib.util.spec_from_file_location("embedding_service_app", _APP_PATH)
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)

REV = "914f7f89142e33e77833254d9c9b90c3cef7303b"


def test_prefixes_match_openvman_gemma_provider():
    """前綴一改，同一個 identity 就會算出跟 openVman 不同的向量。"""
    assert app._format_inputs(["痛風"], "query", None) == [
        "task: question answering | query: 痛風"
    ]
    assert app._format_inputs(["痛風"], "search_query", None) == [
        "task: search result | query: 痛風"
    ]
    assert app._format_inputs(["a", "b"], "document", ["骨科 / 痛風", ""]) == [
        "title: 骨科 / 痛風 | text: a",
        "title: none | text: b",
    ]
    assert app._format_inputs(["a"], "document", None) == ["title: none | text: a"]


def test_identity_matches_backend_contract():
    assert app._build_spec("query")["identity"] == (
        f"gemma:google/embeddinggemma-2:768:float32:l2:query:{REV}"
    )


def test_foreign_identity_is_rejected():
    req = app.EmbedRequest(
        texts=["x"],
        input_type="query",
        identity=f"bge:BAAI/bge-m3:1024:float32:l2:query:{REV}",
    )
    with pytest.raises(HTTPException) as exc:
        app._check_identity(req)
    assert exc.value.status_code == 422


def test_acceptable_identities_containing_ours_pass():
    req = app.EmbedRequest(
        texts=["x"],
        input_type="document",
        acceptable_identities=[
            "bge:BAAI/bge-m3:1024:float32:l2:document:x",
            app._build_spec("document")["identity"],
        ],
    )
    app._check_identity(req)


def test_vectors_are_truncated_and_renormalized(monkeypatch):
    class FakeModel:
        def encode(self, inputs, **kwargs):
            return np.full((len(inputs), 1024), 3.0, dtype=np.float32)

    monkeypatch.setattr(app, "_model", FakeModel())
    rows = app._encode_texts(["a", "b"], "query")
    arr = np.asarray(rows)
    assert arr.shape == (2, 768)
    assert np.allclose(np.linalg.norm(arr, axis=1), 1.0)
