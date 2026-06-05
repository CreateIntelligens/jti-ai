from app.prompts import PromptManager, StorePrompts
from app.routers.general import chat as general_chat
from app.routers.general import prompts as prompt_routes
from app.routers.general.stores import resolve_store_config
from app.services.jti import agent_prompts as jti_prompts


class InMemoryPromptManager(PromptManager):
    def __init__(self):
        self.stores = {}

    def get_store_prompts(self, store_name: str) -> StorePrompts:
        return self.stores.get(store_name, StorePrompts(store_name=store_name))

    def save_store_prompts(self, store_prompts: StorePrompts):
        self.stores[store_prompts.store_name] = store_prompts


def test_managed_default_prompt_exposes_english_persona_for_copying():
    item = prompt_routes._system_default_prompt_item("__jti__en")

    assert item["content"] == jti_prompts.PERSONA["zh"]
    assert item["content_en"] == jti_prompts.PERSONA["en"]
    assert item["response_rule_sections"]["en"] == jti_prompts.DEFAULT_RESPONSE_RULE_SECTIONS["en"]


def test_prompt_manager_create_and_update_preserve_english_persona():
    manager = InMemoryPromptManager()

    created = manager.create_prompt(
        store_name="store_prompt_en",
        name="Custom",
        content="中文 persona",
        content_en="English persona",
    )

    assert created.content_en == "English persona"

    updated = manager.update_prompt(
        store_name="store_prompt_en",
        prompt_id=created.id,
        content_en="Updated English persona",
    )

    assert updated.content_en == "Updated English persona"


def test_general_prompt_handlers_pass_content_en_to_manager(monkeypatch):
    manager = InMemoryPromptManager()
    monkeypatch.setattr(prompt_routes.deps, "prompt_manager", manager)

    created = prompt_routes.create_store_prompt(
        "store_prompt_handler_en",
        prompt_routes.CreatePromptRequest(
            name="Custom",
            content="中文 persona",
            content_en="English persona",
        ),
    )

    assert created["content_en"] == "English persona"

    updated = prompt_routes.update_store_prompt(
        "store_prompt_handler_en",
        created["id"],
        prompt_routes.UpdatePromptRequest(content_en="Updated English persona"),
    )

    assert updated["content_en"] == "Updated English persona"


def test_general_english_store_custom_prompt_uses_english_persona(monkeypatch):
    manager = InMemoryPromptManager()
    manager.create_prompt(
        store_name="__jti__en",
        name="Custom JTI English",
        content="中文 persona marker",
        content_en="English persona marker",
        response_rule_sections={
            "zh": {"response_style": "中文 response style marker"},
            "en": {"response_style": "English response style marker"},
        },
    )
    monkeypatch.setattr(general_chat.deps, "prompt_manager", manager)

    instruction = general_chat._resolve_general_system_instruction(
        "__jti__en",
        {"role": "admin"},
        resolve_store_config("__jti__en"),
    )

    assert "English persona marker" in instruction
    assert "English response style marker" in instruction
    assert "中文 persona marker" not in instruction
    assert "中文 response style marker" not in instruction
