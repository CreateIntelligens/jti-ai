"""Regression tests for PromptManager.save_store_prompts field deletion.

設為 None 的欄位必須真的從 MongoDB 移除。單用 $set + exclude_none 時
這些欄位不會進 payload，$set 又只動它收到的欄位，舊值就永遠留著
（JTI legacy 遷移把 jti_persona_by_prompt 設 None 卻清不掉即是此坑）。
"""

from unittest.mock import MagicMock

from app.prompts import PromptManager, StorePrompts


def _make_manager() -> tuple[PromptManager, MagicMock]:
    """建立跳過真實連線的 PromptManager，回傳 (manager, collection mock)。"""
    manager = PromptManager.__new__(PromptManager)
    collection = MagicMock()
    manager.collection = collection
    return manager, collection


def _captured_update(collection: MagicMock) -> dict:
    return collection.update_one.call_args[0][1]


def test_none_fields_are_unset():
    manager, collection = _make_manager()
    store_prompts = StorePrompts(store_name="__jti__")
    store_prompts.jti_profiles_by_prompt = {"prompt_1": {"persona": {"zh": "x"}}}
    store_prompts.jti_persona_by_prompt = None

    manager.save_store_prompts(store_prompts)

    update = _captured_update(collection)
    assert "jti_persona_by_prompt" in update["$unset"]
    assert "jti_persona_by_prompt" not in update["$set"]


def test_populated_fields_are_set_not_unset():
    manager, collection = _make_manager()
    store_prompts = StorePrompts(store_name="__jti__")
    profiles = {"prompt_1": {"persona": {"zh": "x"}}}
    store_prompts.jti_profiles_by_prompt = profiles

    manager.save_store_prompts(store_prompts)

    update = _captured_update(collection)
    assert update["$set"]["jti_profiles_by_prompt"] == profiles
    assert "jti_profiles_by_prompt" not in update.get("$unset", {})


def test_active_prompt_id_cleared_via_unset():
    """active_prompt_id 設 None 時同樣要被清掉（原本靠特例補寫）。"""
    manager, collection = _make_manager()
    store_prompts = StorePrompts(store_name="__jti__")
    store_prompts.active_prompt_id = None

    manager.save_store_prompts(store_prompts)

    update = _captured_update(collection)
    assert "active_prompt_id" in update["$unset"]


def test_no_unset_key_when_nothing_to_clear():
    """全部欄位都有值時不應送出空的 $unset。"""
    manager, collection = _make_manager()
    store_prompts = StorePrompts(store_name="__jti__")
    full = store_prompts.model_dump()
    for key, value in full.items():
        if value is None:
            setattr(store_prompts, key, {} if key.endswith("_by_prompt") else "x")

    manager.save_store_prompts(store_prompts)

    update = _captured_update(collection)
    assert "$unset" not in update
