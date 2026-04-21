"""HCIoT Persona 管理 API（使用 shared persona router factory）。"""

from app.routers._shared.persona_router import (
    FlatPersonaAdapter,
    PersonaRouterConfig,
    build_persona_router,
)
from app.services.hciot.agent_prompts import PERSONA
from app.services.hciot.main_agent import main_agent
from app.services.hciot.runtime_settings import (
    HciotRuntimeSettings,
    RULE_SECTION_FIELDS,
    SYSTEM_DEFAULT_PROMPT_ID,
    load_runtime_settings_from_prompt_manager,
    save_runtime_settings_to_prompt_manager,
)

_config = PersonaRouterConfig(
    tag="HCIoT Prompts",
    store_name_zh="__hciot__",
    store_name_en="__hciot__en",
    system_default_prompt_id=SYSTEM_DEFAULT_PROMPT_ID,
    persona_defaults={
        "zh": PERSONA.get("zh", ""),
        "en": PERSONA.get("en", PERSONA.get("zh", "")),
    },
    default_prompt_names={
        "zh": "預設衛教助手設定",
        "en": "預設衛教助手設定",
    },
    custom_prompt_name_prefix={
        "zh": "自訂衛教助手設定",
        "en": "自訂衛教助手設定",
    },
    persona_adapter=FlatPersonaAdapter(attr="hciot_persona_by_prompt"),
    runtime_settings_type=HciotRuntimeSettings,
    runtime_settings_load=load_runtime_settings_from_prompt_manager,
    runtime_settings_save=save_runtime_settings_to_prompt_manager,
    runtime_settings_rule_section_fields=tuple(RULE_SECTION_FIELDS),
    max_response_chars_ge=30,
    max_response_chars_le=100,
    main_agent=main_agent,
    clone_success_message="已複製預設衛教助手設定並啟用",
    runtime_update_message="已更新回覆規則",
    runtime_default_readonly_message="預設設定為唯讀，請先建立副本並啟用後再編輯。",
    delete_clears_runtime_overrides=True,
    runtime_overrides_attr="hciot_runtime_settings_by_prompt",
)

router = build_persona_router(_config)
