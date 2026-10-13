"""Map management endpoints to stable audit action names."""

_USER_ACTIONS = {
    "list_users": "user.list",
    "create_user": "user.create",
    "set_user_disabled": "user.disable",
    "delete_user": "user.delete",
}
_API_KEY_ACTIONS = {
    "list_api_keys": "api_key.list",
    "create_api_key": "api_key.create",
    "get_api_key": "api_key.read",
    "reveal_api_key": "api_key.reveal",
    "update_api_key": "api_key.update",
    "delete_api_key": "api_key.delete",
}
_KB_ACTIONS = {
    "upload_knowledge_file": "kb.file.upload",
    "update_file_content": "kb.file.update",
    "update_file_metadata": "kb.file.update",
    "delete_knowledge_file": "kb.file.delete",
    "save_topic_csv_merged": "kb.file.update",
}
_PROMPT_ACTIONS = {
    "create_prompt": "prompt.update",
    "clone_default_prompt": "prompt.update",
    "update_prompt": "prompt.update",
    "delete_prompt": "prompt.update",
    "set_active_prompt": "prompt.update",
    "update_runtime_settings": "prompt.update",
    "create_store_prompt": "prompt.update",
    "update_store_prompt": "prompt.update",
    "delete_store_prompt": "prompt.update",
    "set_active_store_prompt": "prompt.update",
    "update_quiz_config": "quiz.config.update",
}
_TOPIC_ACTIONS = {
    "create_topic": "kb.topic.create",
    "reorder_topics": "kb.topic.update",
    "delete_topics_batch": "kb.topic.delete",
    "update_category_visibility": "kb.topic.update",
    "update_topic": "kb.topic.update",
    "delete_topic": "kb.topic.delete",
}
_QUIZ_BANK_ACTIONS = {
    "create_bank": "quiz.bank.create",
    "delete_bank": "quiz.bank.delete",
    "activate_bank": "quiz.bank.update",
    "create_question": "quiz.question.create",
    "update_question": "quiz.question.update",
    "delete_question": "quiz.question.delete",
    "create_quiz_set": "quiz.set.create",
    "delete_quiz_set": "quiz.set.delete",
    "activate_quiz_set": "quiz.set.update",
    "update_quiz_result": "quiz.result.update",
    "import_data": "quiz.bank.import",
}

_MODULE_ACTIONS = {
    "app.routers.admin_audit": {"list_audit_logs": "audit_log.read"},
    "app.routers.auth_routes": {
        "login": "auth.login",
    },
    "app.routers.general.users": _USER_ACTIONS,
    "app.routers.general.api_keys": _API_KEY_ACTIONS,
    "app.routers._shared.qa_kb_router": _KB_ACTIONS,
    "app.routers._shared.persona_router": _PROMPT_ACTIONS,
    "app.routers.general.prompts": _PROMPT_ACTIONS,
    "app.routers._shared.plain_topics_admin": _TOPIC_ACTIONS,
    "app.routers.general.topics_admin": _TOPIC_ACTIONS,
    "app.routers.hciot.topics_admin": _TOPIC_ACTIONS,
    "app.routers.general.quiz_bank": _QUIZ_BANK_ACTIONS,
    "app.routers.jti.quiz_bank": _QUIZ_BANK_ACTIONS,
    "app.routers.esg.quiz_bank": _QUIZ_BANK_ACTIONS,
    "app.routers.general.images": {
        "upload_image": "image.upload",
        "delete_image": "image.delete",
    },
    "app.routers.hciot.images": {
        "upload_image": "image.upload",
        "delete_image": "image.delete",
        "delete_unused_images": "image.delete",
    },
    "app.routers.general.stores": {
        "create_store": "store.create",
        "delete_store": "store.delete",
        "upload_file": "kb.file.upload",
        "delete_file": "kb.file.delete",
        "update_store_file_content": "kb.file.update",
    },
    "app.routers.admin_rag": {"reindex_rag": "rag.reindex"},
    "app.routers.general.knowledge": {"reindex_store": "rag.reindex"},
    "app.routers.general.db_sync": {"trigger_db_sync": "db.sync"},
    "app.routers.general.chat": {
        "delete_general_conversations": "conversation.delete",
    },
    "app.routers.jti.chat": {"delete_conversations": "conversation.delete"},
    "app.routers.hciot.chat": {"delete_conversations": "conversation.delete"},
    "app.routers.esg.chat": {"delete_conversations": "conversation.delete"},
}


def resolve_action(module: str, name: str, method: str) -> str | None:
    """Resolve known management routes without logging normal chat activity."""
    if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return None
    return _MODULE_ACTIONS.get(module, {}).get(name)
