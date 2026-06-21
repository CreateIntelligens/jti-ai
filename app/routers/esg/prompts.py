"""ESG persona management API."""

from app.routers._shared.persona_router import (
    FlatPersonaAdapter,
    PersonaRouterConfig,
    build_persona_router,
)
from app.services.esg.agent_prompts import PERSONA
from app.services.esg.main_agent import main_agent
from app.services.esg.runtime_settings import (
    EsgRuntimeSettings,
    RULE_SECTION_FIELDS,
    SYSTEM_DEFAULT_PROMPT_ID,
    load_runtime_settings_from_prompt_manager,
    save_runtime_settings_to_prompt_manager,
)

_config = PersonaRouterConfig(
    tag="ESG Prompts",
    store_name_zh="__esg__",
    store_name_en="__esg__en",
    system_default_prompt_id=SYSTEM_DEFAULT_PROMPT_ID,
    persona_defaults={
        "zh": PERSONA.get("zh", ""),
        "en": PERSONA.get("en", PERSONA.get("zh", "")),
    },
    default_prompt_names={"zh": "預設 ESG 助手設定", "en": "預設 ESG 助手設定"},
    custom_prompt_name_prefix={"zh": "自訂 ESG 助手設定", "en": "自訂 ESG 助手設定"},
    persona_adapter=FlatPersonaAdapter(attr="esg_persona_by_prompt"),
    runtime_settings_type=EsgRuntimeSettings,
    runtime_settings_load=load_runtime_settings_from_prompt_manager,
    runtime_settings_save=save_runtime_settings_to_prompt_manager,
    runtime_settings_rule_section_fields=tuple(RULE_SECTION_FIELDS),
    max_response_chars_ge=0,
    max_response_chars_le=600,
    main_agent=main_agent,
    prompt_index_attr="esg_prompt_index",
    active_prompt_id_attr="esg_active_prompt_id",
    clone_success_message="已複製預設 ESG 助手設定並啟用",
    runtime_update_message="已更新 ESG 回覆規則設定",
    runtime_default_readonly_message=(
        "預設 ESG 助手設定為唯讀，請先建立副本並啟用後再編輯。"
    ),
    delete_clears_runtime_overrides=True,
    runtime_overrides_attr="esg_runtime_settings_by_prompt",
)

router = build_persona_router(_config)
