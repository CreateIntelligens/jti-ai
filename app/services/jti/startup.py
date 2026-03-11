"""
JTI-specific startup / initialization logic.

Called from deps.init_managers() during application startup.
"""

import logging
from typing import Dict, Optional

from app.services.jti.agent_prompts import PERSONA
from app.services.jti.runtime_settings import SYSTEM_DEFAULT_PROMPT_ID

logger = logging.getLogger(__name__)

JTI_STORES = ("__jti__", "__jti__en")


def jti_startup(prompt_manager) -> None:
    """Run all JTI-specific initialization tasks."""
    _init_jti_default_prompt(prompt_manager)
    _migrate_jti_profile_storage(prompt_manager)
    _seed_quiz_data()


def _init_jti_default_prompt(prompt_manager) -> None:
    """清理 MongoDB 中舊的 system_default prompt（向下相容）

    預設人物設定現在直接從 agent_prompts.py 讀取，不再存 MongoDB。
    """
    if not prompt_manager:
        return

    for store_name in JTI_STORES:
        prompts = prompt_manager.list_prompts(store_name)
        has_old_default = any(p.id == SYSTEM_DEFAULT_PROMPT_ID for p in prompts)

        if has_old_default:
            # 移除舊的 system_default，預設人物設定改為從程式碼讀取
            store_prompts = prompt_manager._load_store_prompts(store_name)
            store_prompts.prompts = [
                p for p in store_prompts.prompts if p.id != SYSTEM_DEFAULT_PROMPT_ID
            ]
            # 如果啟用的是 system_default，清除啟用狀態（回到使用程式碼預設）
            if store_prompts.active_prompt_id == SYSTEM_DEFAULT_PROMPT_ID:
                store_prompts.active_prompt_id = None
            prompt_manager._save_store_prompts(store_prompts)
            print(
                f"[Startup] 🔄 已清理 MongoDB 中的舊預設人物設定 "
                f"(store={store_name}, id={SYSTEM_DEFAULT_PROMPT_ID})"
            )

    print("[Startup] ✅ JTI 預設人物設定從 agent_prompts.py 讀取（地端唯讀）")


def _get_default_persona_pair() -> Dict[str, str]:
    zh = PERSONA.get("zh", "")
    return {
        "zh": zh,
        "en": PERSONA.get("en", zh),
    }


def _build_fallback_persona_pair(content: Optional[str]) -> Dict[str, str]:
    base_content = content or ""
    if base_content in (PERSONA.get("zh"), PERSONA.get("en")):
        return _get_default_persona_pair()
    return {
        "zh": base_content,
        "en": base_content,
    }


def _normalize_persona_pair(raw_pair, fallback_content: Optional[str]) -> Dict[str, str]:
    fallback = _build_fallback_persona_pair(fallback_content)
    if not isinstance(raw_pair, dict):
        return fallback
    normalized: Dict[str, str] = {}
    for lang in ("zh", "en"):
        value = raw_pair.get(lang)
        normalized[lang] = value if isinstance(value, str) and value.strip() else fallback[lang]
    return normalized


def _migrate_jti_profile_storage(prompt_manager) -> None:
    """Merge legacy persona/runtime maps into one `jti_profiles_by_prompt` map."""
    if not prompt_manager:
        return

    for store_name in JTI_STORES:
        store_prompts = prompt_manager._load_store_prompts(store_name)

        raw_profiles = getattr(store_prompts, "jti_profiles_by_prompt", None)
        profiles_map: Dict[str, Dict] = raw_profiles if isinstance(raw_profiles, dict) else {}
        changed = not isinstance(raw_profiles, dict)

        raw_persona_map = getattr(store_prompts, "jti_persona_by_prompt", None)
        legacy_persona_map = raw_persona_map if isinstance(raw_persona_map, dict) else {}
        raw_runtime_map = getattr(store_prompts, "jti_runtime_settings_by_prompt", None)
        legacy_runtime_map = raw_runtime_map if isinstance(raw_runtime_map, dict) else {}
        raw_runtime_single = getattr(store_prompts, "jti_runtime_settings", None)
        legacy_runtime_single = raw_runtime_single if isinstance(raw_runtime_single, dict) else None

        default_legacy_runtime = legacy_runtime_map.get(SYSTEM_DEFAULT_PROMPT_ID)
        if not isinstance(default_legacy_runtime, dict):
            default_legacy_runtime = legacy_runtime_single

        for prompt in store_prompts.prompts:
            profile = profiles_map.get(prompt.id)
            if not isinstance(profile, dict):
                profile = {}
                changed = True

            raw_persona = profile.get("persona")
            if not isinstance(raw_persona, dict):
                legacy_persona = legacy_persona_map.get(prompt.id)
                profile["persona"] = _normalize_persona_pair(legacy_persona, prompt.content)
                changed = True

            raw_runtime = profile.get("runtime_settings")
            if not isinstance(raw_runtime, dict):
                legacy_runtime = legacy_runtime_map.get(prompt.id)
                if not isinstance(legacy_runtime, dict):
                    legacy_runtime = default_legacy_runtime
                if isinstance(legacy_runtime, dict):
                    profile["runtime_settings"] = legacy_runtime
                    changed = True

            profiles_map[prompt.id] = profile

        default_profile = profiles_map.get(SYSTEM_DEFAULT_PROMPT_ID)
        if not isinstance(default_profile, dict):
            default_profile = {}
            changed = True
        if not isinstance(default_profile.get("persona"), dict):
            default_profile["persona"] = _get_default_persona_pair()
            changed = True
        if not isinstance(default_profile.get("runtime_settings"), dict) and isinstance(default_legacy_runtime, dict):
            default_profile["runtime_settings"] = default_legacy_runtime
            changed = True
        profiles_map[SYSTEM_DEFAULT_PROMPT_ID] = default_profile

        for legacy_field in ("jti_runtime_settings", "jti_runtime_settings_by_prompt", "jti_persona_by_prompt"):
            if getattr(store_prompts, legacy_field, None) is not None:
                setattr(store_prompts, legacy_field, None)
                changed = True

        if changed:
            store_prompts.jti_profiles_by_prompt = profiles_map
            prompt_manager._save_store_prompts(store_prompts)
            print(f"[Startup] ✅ 已整併 JTI 人物設定/回覆規則儲存格式 (store={store_name})")


def _seed_quiz_data() -> None:
    """Seed quiz bank and quiz results from JSON into MongoDB."""
    from .migrate_quiz_bank import migrate_quiz_bank, migrate_quiz_results
    migrate_quiz_bank()
    migrate_quiz_results()
