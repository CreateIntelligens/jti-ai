from types import SimpleNamespace

from app.routers.general import stores


def test_resolve_managed_store_context_matches_env_ids(monkeypatch):
    monkeypatch.setenv("GEMINI_FILE_SEARCH_STORE_ID_ZH", "jti-zh-id")
    monkeypatch.setenv("GEMINI_FILE_SEARCH_STORE_ID_EN", "fileSearchStores/jti-en-id")
    monkeypatch.setenv("HCIOT_STORE_ID_ZH", "hciot-zh-id")
    monkeypatch.setenv("HCIOT_STORE_ID_EN", "hciot-en-id")

    assert stores._resolve_managed_store_context("fileSearchStores/jti-zh-id") == {
        "managed_app": "jti",
        "managed_language": "zh",
    }
    assert stores._resolve_managed_store_context("fileSearchStores/jti-en-id") == {
        "managed_app": "jti",
        "managed_language": "en",
    }
    assert stores._resolve_managed_store_context("fileSearchStores/hciot-zh-id") == {
        "managed_app": "hciot",
        "managed_language": "zh",
    }
    assert stores._resolve_managed_store_context("fileSearchStores/hciot-en-id") == {
        "managed_app": "hciot",
        "managed_language": "en",
    }


def test_list_stores_includes_managed_metadata(monkeypatch):
    fake_manager = SimpleNamespace(
        list_stores=lambda: [
            SimpleNamespace(name="fileSearchStores/jti-zh-id", display_name="JTI"),
            SimpleNamespace(name="fileSearchStores/custom-id", display_name="Custom"),
        ]
    )
    monkeypatch.setattr(stores, "_get_or_create_manager", lambda: fake_manager)
    monkeypatch.setenv("GEMINI_FILE_SEARCH_STORE_ID_ZH", "jti-zh-id")

    result = stores.list_stores(auth={"role": "admin"})

    assert result == [
        {
            "name": "fileSearchStores/jti-zh-id",
            "display_name": "JTI",
            "managed_app": "jti",
            "managed_language": "zh",
        },
        {
            "name": "fileSearchStores/custom-id",
            "display_name": "Custom",
            "managed_app": None,
            "managed_language": None,
        },
    ]
