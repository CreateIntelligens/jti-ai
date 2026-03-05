"""
JTI-specific startup / initialization logic.

Called from deps.init_managers() during application startup.
"""

import logging

logger = logging.getLogger(__name__)


def jti_startup(prompt_manager) -> None:
    """Run all JTI-specific initialization tasks."""
    _init_jti_default_prompt(prompt_manager)
    _seed_quiz_data()


def _init_jti_default_prompt(prompt_manager) -> None:
    """清理 MongoDB 中舊的 system_default prompt（向下相容）

    預設人物設定現在直接從 agent_prompts.py 讀取，不再存 MongoDB。
    """
    if not prompt_manager:
        return

    JTI_STORE = "__jti__"
    DEFAULT_ID = "system_default"

    prompts = prompt_manager.list_prompts(JTI_STORE)
    has_old_default = any(p.id == DEFAULT_ID for p in prompts)

    if has_old_default:
        # 移除舊的 system_default，預設人物設定改為從程式碼讀取
        store_prompts = prompt_manager._load_store_prompts(JTI_STORE)
        store_prompts.prompts = [p for p in store_prompts.prompts if p.id != DEFAULT_ID]
        # 如果啟用的是 system_default，清除啟用狀態（回到使用程式碼預設）
        if store_prompts.active_prompt_id == DEFAULT_ID:
            store_prompts.active_prompt_id = None
        prompt_manager._save_store_prompts(store_prompts)
        print(f"[Startup] 🔄 已清理 MongoDB 中的舊預設人物設定 (id={DEFAULT_ID})")

    print("[Startup] ✅ JTI 預設人物設定從 agent_prompts.py 讀取（地端唯讀）")


def _seed_quiz_data() -> None:
    """Seed quiz bank & color results from JSON → MongoDB."""
    from .migrate_quiz_bank import migrate_quiz_bank, migrate_color_results
    migrate_quiz_bank()
    migrate_color_results()
