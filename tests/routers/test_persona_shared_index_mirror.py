"""app-specific prompt index 必須鏡射到共用的 prompts[] / active_prompt_id。

主頁（PromptPanel → /stores/{store}/prompts）讀共用欄位，各 app 的專用設定頁
讀自己的 *_prompt_index。ESG 兩邊都有值所以主頁串得回來，JTI/HCIoT 只寫了
專屬欄位，主頁就只剩預設 —— 使用者看到的是「自訂 prompt 不見了」。
"""

import pytest

from app.prompts import Prompt, PromptIndexEntry, StorePrompts
from app.routers._shared.persona_router import (
    mirror_active_to_shared,
    mirror_index_to_shared,
)
from app.routers.jti.prompts import _config as jti_config


@pytest.fixture
def store_prompts():
    return StorePrompts(store_name="__jti__")


def _set_index(store_prompts, entries):
    mirror_index_to_shared(store_prompts, entries)


def _set_active(store_prompts, prompt_id):
    mirror_active_to_shared(store_prompts, prompt_id)


def test_index_mirrors_into_shared_prompts(store_prompts):
    entry = PromptIndexEntry(name="Lady X")
    _set_index(store_prompts, [entry])

    assert [p.id for p in store_prompts.prompts] == [entry.id]
    assert [p.name for p in store_prompts.prompts] == ["Lady X"]


def test_active_id_mirrors_into_shared(store_prompts):
    entry = PromptIndexEntry(name="Lady X")
    _set_index(store_prompts, [entry])
    _set_active(store_prompts, entry.id)

    assert store_prompts.active_prompt_id == entry.id


def test_clearing_active_clears_shared(store_prompts):
    entry = PromptIndexEntry(name="Lady X")
    _set_index(store_prompts, [entry])
    _set_active(store_prompts, entry.id)
    _set_active(store_prompts, None)

    assert store_prompts.active_prompt_id is None


def test_removing_entry_removes_from_shared(store_prompts):
    keep = PromptIndexEntry(name="保留")
    drop = PromptIndexEntry(name="刪除")
    _set_index(store_prompts, [keep, drop])
    _set_index(store_prompts, [keep])

    assert [p.id for p in store_prompts.prompts] == [keep.id]


def test_mirror_preserves_existing_shared_content(store_prompts):
    """共用 prompts[] 既有的 content 不該被鏡射覆蓋掉。"""
    entry = PromptIndexEntry(name="Lady X")
    store_prompts.prompts = [
        Prompt(id=entry.id, name="舊名字", content="既有內容")
    ]
    _set_index(store_prompts, [entry])

    mirrored = store_prompts.prompts[0]
    assert mirrored.id == entry.id
    assert mirrored.name == "Lady X"      # 名字跟著 index 更新
    assert mirrored.content == "既有內容"  # content 保留


def test_mirror_copies_persona_content_for_store_language(store_prompts):
    """persona 是 zh/en 一對，共用 content 要取這個 store 對應的那半。"""
    entry = PromptIndexEntry(name="Lady X")
    store_prompts.jti_profiles_by_prompt = {
        entry.id: {"persona": {"zh": "中文人設", "en": "English persona"}}
    }

    mirror_index_to_shared(
        store_prompts,
        [entry],
        persona_adapter=jti_config.persona_adapter,
        language="zh",
    )
    assert store_prompts.prompts[0].content == "中文人設"

    mirror_index_to_shared(
        store_prompts,
        [entry],
        persona_adapter=jti_config.persona_adapter,
        language="en",
    )
    assert store_prompts.prompts[0].content == "English persona"


def test_mirror_without_adapter_keeps_existing_content(store_prompts):
    """沒有 adapter 時不要把既有 content 洗成空字串。"""
    entry = PromptIndexEntry(name="Lady X")
    store_prompts.prompts = [Prompt(id=entry.id, name="舊", content="既有內容")]

    mirror_index_to_shared(store_prompts, [entry])

    assert store_prompts.prompts[0].content == "既有內容"
