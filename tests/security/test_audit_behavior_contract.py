"""Guard the existing API contract while adding passive observations."""

import ast
import asyncio
import shutil
import subprocess
from contextlib import AsyncExitStack
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_EXISTING_MODULES = (
    "app/auth.py",
    "app/main.py",
    "app/users.py",
    "app/routers/admin_rag.py",
    "app/routers/auth_routes.py",
    "app/routers/_shared/persona_router.py",
    "app/routers/_shared/plain_topics_admin.py",
    "app/routers/_shared/qa_kb_router.py",
    "app/routers/esg/chat.py",
    "app/routers/esg/quiz_bank.py",
    "app/routers/general/api_keys.py",
    "app/routers/general/chat.py",
    "app/routers/general/db_sync.py",
    "app/routers/general/images.py",
    "app/routers/general/knowledge.py",
    "app/routers/general/prompts.py",
    "app/routers/general/quiz_bank.py",
    "app/routers/general/stores.py",
    "app/routers/general/topics_admin.py",
    "app/routers/general/users.py",
    "app/routers/hciot/chat.py",
    "app/routers/hciot/images.py",
    "app/routers/hciot/topics_admin.py",
    "app/routers/jti/chat.py",
    "app/routers/jti/quiz_bank.py",
)
_OBSERVER_CALLS = {"observe_actor", "observe_login_result"}


def _git_output(*args):
    if shutil.which("git") is None:
        pytest.skip("Git checkout metadata is unavailable")
    checkout = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    if checkout.returncode or checkout.stdout.strip() != "true":
        pytest.skip("Git checkout metadata is unavailable")
    return subprocess.run(
        ["git", *args],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _head_source(path):
    return _git_output("show", f"HEAD:{path}")


def _call_name(node, name):
    return isinstance(node, ast.Name) and node.id == name


class _WithoutAuditObservations(ast.NodeTransformer):
    def visit_ImportFrom(self, node):
        if node.module == "app.services.audit_log":
            node.names = [
                alias for alias in node.names
                if alias.name not in {*_OBSERVER_CALLS, "AuditRoute"}
            ]
            return node if node.names else None
        if node.module == "routers.admin_audit" and node.level == 1:
            if len(node.names) == 1:
                alias = node.names[0]
                if alias.name == "router" and alias.asname == "admin_audit_router":
                    return None
        return node

    def visit_Expr(self, node):
        value = node.value
        if isinstance(value, ast.Call):
            if any(_call_name(value.func, name) for name in _OBSERVER_CALLS):
                return None
            if (
                isinstance(value.func, ast.Attribute)
                and _call_name(value.func.value, "app")
                and value.func.attr == "include_router"
                and len(value.args) == 1
                and _call_name(value.args[0], "admin_audit_router")
                and not value.keywords
            ):
                return None
        return self.generic_visit(node)

    def visit_Call(self, node):
        if _call_name(node.func, "APIRouter"):
            node.keywords = [
                keyword for keyword in node.keywords
                if not (
                    keyword.arg == "route_class"
                    and _call_name(keyword.value, "AuditRoute")
                )
            ]
        return self.generic_visit(node)


def _contract(source):
    tree = _WithoutAuditObservations().visit(ast.parse(source))
    return ast.dump(tree, include_attributes=False)


@pytest.mark.parametrize("path", _EXISTING_MODULES)
def test_existing_code_only_adds_passive_audit_observations(path):
    # Full AST equality also guards permissions, dependencies and cookie settings.
    assert _contract((_ROOT / path).read_text()) == _contract(_head_source(path))


def _registered_routers(source):
    routers = []
    tree = _WithoutAuditObservations().visit(ast.parse(source))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if _call_name(node.func.value, "app") and node.func.attr == "include_router":
            routers.append(ast.dump(node, include_attributes=False))
    return routers


def test_existing_router_order_is_unchanged():
    assert _registered_routers(
        (_ROOT / "app/main.py").read_text()
    ) == _registered_routers(
        _head_source("app/main.py")
    )


def test_new_audit_router_only_exposes_the_read_api():
    tree = ast.parse((_ROOT / "app/routers/admin_audit.py").read_text())
    endpoints = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and _call_name(decorator.func.value, "router")
            ):
                endpoints.append((decorator.func.attr, decorator.args[0].value))
    assert endpoints == [("get", "/audit-logs")]


def test_runtime_and_deployment_configuration_remains_unchanged():
    tracked = _git_output(
        "ls-files", "docker", "docker-compose.yml", "frontend/vite.config.ts"
    ).splitlines()
    assert tracked
    for path in tracked:
        assert (_ROOT / path).read_text() == _head_source(path), path


def test_status_observation_preserves_the_original_exception(monkeypatch):
    from fastapi import Request

    from app.services import audit_actions, audit_log

    class OriginalError(Exception):
        @property
        def status_code(self):
            raise ValueError("Status observation unavailable")

    original = OriginalError("Original endpoint failure")

    async def endpoint():
        raise original

    monkeypatch.setattr(audit_actions, "resolve_action", lambda *args: "user.create")
    monkeypatch.setattr(audit_log, "record_audit", lambda *args, **kwargs: None)
    route = audit_log.AuditRoute("/sample", endpoint, methods=["POST"])

    async def run():
        async with AsyncExitStack() as stack:
            request = Request({
                "type": "http", "method": "POST", "path": "/sample",
                "headers": [], "query_string": b"",
                "fastapi_middleware_astack": stack,
                "fastapi_inner_astack": stack,
                "fastapi_function_astack": stack,
            })
            await route.get_route_handler()(request)

    with pytest.raises(OriginalError) as caught:
        asyncio.run(run())
    assert caught.value is original


def test_observer_metadata_getter_failure_keeps_login_result(monkeypatch):
    from fastapi import Request, Response

    import app.users as users_module
    from app.routers import auth_routes
    from app.services import audit_log

    class UserMetadata:
        id = "user_sample"
        role = "user"
        scope = "general"
        disabled = False
        password_hash = "stored-hash"

        @property
        def username(self):
            raise ValueError("Optional identity observation unavailable")

    user = UserMetadata()
    manager = object.__new__(users_module.UserManager)
    manager.collection = MagicMock()
    manager.collection.find_one.return_value = {"id": user.id}
    manager._user_from_doc = lambda doc: user
    manager.get_by_username = MagicMock()
    monkeypatch.setattr(auth_routes.deps, "user_manager", manager)
    password_check = MagicMock(return_value=True)
    monkeypatch.setattr(users_module, "verify_password", password_check)
    monkeypatch.setattr(auth_routes, "create_session_token", lambda *args: "fixed-token")
    queued = []
    monkeypatch.setattr(audit_log, "_enqueue_record", queued.append)
    request = Request({
        "type": "http", "method": "POST", "path": "/api/auth/login",
        "headers": [], "query_string": b"",
    })
    context = audit_log._request_context.set(request)
    try:
        response = Response()
        result = auth_routes.login(
            auth_routes.LoginRequest(username="sample", password="sample"),
            response,
        )
    finally:
        audit_log._request_context.reset(context)
    assert result == {"token": "fixed-token", "role": "user", "scope": "general"}
    assert "session=fixed-token" in response.headers["set-cookie"]
    manager.collection.find_one.assert_called_once_with({"username": "sample"})
    password_check.assert_called_once_with("sample", "stored-hash")
    manager.get_by_username.assert_not_called()
    assert queued == ["Audit identity observation failed"]
