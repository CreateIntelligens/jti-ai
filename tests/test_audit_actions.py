"""Keep the management audit mapping aligned with router endpoints."""

import ast
from pathlib import Path

from app.services.audit_actions import resolve_action

_ROUTERS = Path(__file__).resolve().parents[1] / "app" / "routers"
_UNRECORDED_ACTIONS = {
    # Logout only clears the caller cookie and performs no authentication.
    ("app.routers.auth_routes", "logout"),
    # These transform inputs or operate ordinary chat/quiz sessions.
    ("app.routers._shared.qa_kb_router", "parse_csv_text"),
    ("app.routers.tts_utils", "create_tts_audio"),
    ("app.routers.general.chat", "start_chat"),
    ("app.routers.general.chat", "send_message"),
    ("app.routers.jti.chat", "create_session"),
    ("app.routers.jti.chat", "chat"),
    ("app.routers.hciot.chat", "create_session"),
    ("app.routers.hciot.chat", "chat"),
    ("app.routers.esg.chat", "create_session"),
    ("app.routers.esg.chat", "chat"),
    ("app.routers.jti.quiz", "quiz_start"),
    ("app.routers.jti.quiz", "quiz_pause"),
    ("app.routers.esg.quiz", "quiz_start"),
    ("app.routers.esg.quiz", "quiz_pause"),
}


def test_all_management_mutations_have_audit_actions():
    missing = []
    for path in _ROUTERS.rglob("*.py"):
        module = ".".join(path.relative_to(_ROUTERS.parent.parent).with_suffix("").parts)
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                route = decorator.func
                if not isinstance(route, ast.Attribute):
                    continue
                if route.attr not in {"post", "put", "patch", "delete"}:
                    continue
                if (module, node.name) in _UNRECORDED_ACTIONS:
                    continue
                if resolve_action(module, node.name, route.attr) is None:
                    missing.append(f"{module}.{node.name}")
    assert missing == []


def test_mapped_routes_use_audit_route_class():
    missing = []
    for path in _ROUTERS.rglob("*.py"):
        module = ".".join(path.relative_to(_ROUTERS.parent.parent).with_suffix("").parts)
        tree = ast.parse(path.read_text())
        audited_routers = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            call = node.value
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                continue
            if call.func.id != "APIRouter":
                continue
            if any(
                keyword.arg == "route_class"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "AuditRoute"
                for keyword in call.keywords
            ):
                audited_routers.update(
                    target.id for target in node.targets if isinstance(target, ast.Name)
                )
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                route = decorator.func
                if not isinstance(route, ast.Attribute):
                    continue
                if resolve_action(module, node.name, route.attr) is None:
                    continue
                if not isinstance(route.value, ast.Name):
                    continue
                if route.value.id not in audited_routers:
                    missing.append(f"{module}.{node.name}")
    assert missing == []


def test_sensitive_reads_are_mapped_without_normal_chat_activity():
    assert resolve_action(
        "app.routers.general.api_keys", "reveal_api_key", "GET"
    ) == "api_key.reveal"
    assert resolve_action(
        "app.routers.general.users", "list_users", "GET"
    ) == "user.list"
    assert resolve_action("app.routers.hciot.chat", "chat", "POST") is None
