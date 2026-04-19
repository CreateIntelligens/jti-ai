"""JTI Persona 管理 API（使用 shared persona router factory）。"""

from app.routers._shared.persona_router import (
    NestedProfilePersonaAdapter,
    PersonaRouterConfig,
    build_persona_router,
)
from app.services.jti.agent_prompts import PERSONA
from app.services.jti.main_agent import main_agent
from app.services.jti.runtime_settings import (
    JtiRuntimeSettings,
    PROFILE_PERSONA_KEY,
    RULE_SECTION_FIELDS,
    SYSTEM_DEFAULT_PROMPT_ID,
    load_runtime_settings_from_prompt_manager,
    save_runtime_settings_to_prompt_manager,
)

_config = PersonaRouterConfig(
    tag="JTI Prompts",
    store_name_zh="__jti__",
    store_name_en="__jti__en",
    system_default_prompt_id=SYSTEM_DEFAULT_PROMPT_ID,
    persona_defaults={
        "zh": PERSONA.get("zh", ""),
        "en": PERSONA.get("en", PERSONA.get("zh", "")),
    },
    default_prompt_names={"zh": "預設人物設定", "en": "預設人物設定"},
    custom_prompt_name_prefix={"zh": "自訂人物設定", "en": "自訂人物設定"},
    persona_adapter=NestedProfilePersonaAdapter(
        attr="jti_profiles_by_prompt",
        key=PROFILE_PERSONA_KEY,
    ),
    runtime_settings_type=JtiRuntimeSettings,
    runtime_settings_load=load_runtime_settings_from_prompt_manager,
    runtime_settings_save=save_runtime_settings_to_prompt_manager,
    runtime_settings_rule_section_fields=tuple(RULE_SECTION_FIELDS),
    max_response_chars_ge=0,
    max_response_chars_le=600,
    main_agent=main_agent,
    clone_success_message="已複製預設人物設定並啟用",
    runtime_update_message="已更新回覆規則設定",
    runtime_default_readonly_message=(
        "預設人物設定的回覆規則為唯讀，請先建立副本並啟用後再編輯。"
    ),
    delete_clears_runtime_overrides=False,
)

router = build_persona_router(_config)
