"""Observe security actions without changing request outcomes."""

import inspect
import json
import logging
import os
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from ipaddress import ip_address
from queue import Queue

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.services.db_names import CONTROL_PLANE_DB_NAME
from app.services.mongo_client import get_raw_mongo_db

logger = logging.getLogger(__name__)
_request_context: ContextVar[Request | None] = ContextVar(
    "audit_request", default=None,
)
_pending: Queue = Queue(maxsize=1024)
_worker_lock = threading.Lock()
_worker: threading.Thread | None = None
_collection = None
_indexes_ready = False
_ACTOR_FIELDS = (
    "role", "user_id", "username", "auth_method", "api_key_id", "api_key_prefix",
)
_TARGET_FIELDS = (
    "id", "username", "store_name", "filename", "image_id", "prompt_id",
    "topic_id", "category_id", "bank_id", "source_type", "language", "disabled",
    "topic_ids", "delete_files", "deleted_image_ids", "uploaded_files",
    "source_types", "force", "filenames", "user_id", "key_id",
    "app", "direction", "dry_run", "set_id", "question_id",
    "session_ids", "name", "phase",
)


def _warn(message: str) -> None:
    try:
        if threading.current_thread() is _worker:
            logger.warning(message)
        else:
            _enqueue_record(message)
    except Exception:
        pass


def observe_actor(request: Request | None = None, **metadata) -> None:
    try:
        request = request or _request_context.get()
        if request is None or getattr(request, "state", None) is None:
            return
        actor = dict(getattr(request.state, "audit_actor", {}))
        user = metadata.pop("user", None)
        if user is not None:
            metadata.update({
                "user_id": user.id, "username": user.username,
                "role": user.role,
            })
        api_key = metadata.pop("api_key", None)
        if api_key is not None:
            metadata.update({
                "api_key_id": api_key.id,
                "api_key_prefix": api_key.key_prefix,
            })
        actor.update({key: value for key, value in metadata.items()
                      if key in _ACTOR_FIELDS})
        request.state.audit_actor = actor
    except Exception:
        _warn("Audit identity observation failed")


def observe_login_result(user, username: str, reason: str | None = None) -> None:
    try:
        request = _request_context.get()
        if request is None:
            return
        observe_actor(request, user=user, username=username,
                      auth_method="anonymous")
        if reason:
            request.state.audit_reason = reason
    except Exception:
        _warn("Audit login observation failed")


def _text(value):
    return value[:512] if isinstance(value, str) else None


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().strip('"')
    if value.startswith("[") and "]" in value:
        value = value[1:value.index("]")]
    try:
        return str(ip_address(value))
    except ValueError:
        return None


def _forwarded_headers(request: Request) -> dict:
    return {
        name: ",".join(request.headers.getlist(name)) or None
        for name in ("x-forwarded-for", "x-real-ip", "forwarded")
    }


def _safe_target(target: dict) -> dict:
    safe = {}
    for field in _TARGET_FIELDS:
        value = target.get(field)
        if isinstance(value, (str, bool, int)):
            safe[field] = _text(value) if isinstance(value, str) else value
        elif isinstance(value, list) and all(
            isinstance(item, str) for item in value
        ):
            safe[field] = [_text(item) for item in value]
    return safe


def derive_client_ip(request: Request) -> str | None:
    peer = request.client.host if request.client else None
    try:
        hops = max(0, int(os.getenv("AUDIT_TRUSTED_PROXY_HOPS", "1")))
    except ValueError:
        hops = 0
    if not hops:
        return peer

    headers = _forwarded_headers(request)
    xff = headers["x-forwarded-for"]
    if xff:
        chain = xff.split(",")
    elif headers["forwarded"]:
        chain = []
        for element in headers["forwarded"].split(","):
            values = [
                part.strip()[4:] for part in element.split(";")
                if part.strip().lower().startswith("for=")
            ]
            chain.append(values[0] if len(values) == 1 else "")
    else:
        chain = [headers["x-real-ip"] or ""]
    # 每個可信代理在右側追加它看到的來源；左側額外值不參與選擇。
    if len(chain) < hops:
        return peer
    return _valid_ip(chain[-hops]) or peer


def get_audit_collection():
    global _collection
    if _collection is None:
        _collection = get_raw_mongo_db(CONTROL_PLANE_DB_NAME)["audit_logs"]
    return _collection


def _persist_record(record: dict) -> None:
    global _indexes_ready
    try:
        collection = get_audit_collection()
        if not _indexes_ready:
            try:
                for keys in (
                    [("timestamp", -1)], [("action", 1)],
                    [("client_ip", 1)], [("actor.user_id", 1)],
                ):
                    collection.create_index(keys)
                _indexes_ready = True
            except Exception:
                _warn("Audit index setup failed")
        collection.insert_one(dict(record))
    except Exception:
        # 例外文字可能含連線憑證或資料；只記固定訊息。
        _warn("Audit database write failed; shared file record retained")


def _emit_file_record(record: dict) -> None:
    try:
        logger.info(json.dumps(record, default=str, ensure_ascii=False))
    except Exception:
        _warn("Audit file write failed")


def _drain_records() -> None:
    while True:
        record = _pending.get()
        try:
            if record is None:
                return
            if isinstance(record, str):
                _warn(record)
                continue
            _emit_file_record(record)
            _persist_record(record)
        except Exception:
            _warn("Audit background write failed")
        finally:
            _pending.task_done()


def _enqueue_record(record: dict) -> None:
    global _worker
    _pending.put_nowait(record)
    # 忙碌時只入列，不等另一個請求啟動 writer。
    if _worker_lock.acquire(blocking=False):
        try:
            if _worker is None or not _worker.is_alive():
                _worker = threading.Thread(
                    target=_drain_records, name="audit-writer", daemon=True,
                )
                _worker.start()
        finally:
            _worker_lock.release()


def record_audit(
    request: Request,
    action: str,
    result: str,
    *,
    reason: str | None = None,
    actor: dict | None = None,
    target: dict | None = None,
) -> None:
    """Queue safe metadata; both persistence destinations run off-request."""
    try:
        source_actor = actor or getattr(request.state, "audit_actor", {})
        safe_actor = {
            field: _text(source_actor.get(field)) for field in _ACTOR_FIELDS
        }
        safe_actor["auth_method"] = safe_actor["auth_method"] or "anonymous"
        if safe_actor["api_key_prefix"]:
            safe_actor["api_key_prefix"] = safe_actor["api_key_prefix"][:10] + "..."
        record = {
            "timestamp": datetime.now(timezone.utc),
            "action": action,
            "result": result,
            "reason": reason,
            "actor": safe_actor,
            "target": _safe_target(target or {}),
            "client_ip": derive_client_ip(request),
            "forwarded_chain": _forwarded_headers(request),
            "peer_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "method": request.method,
            # 查詢字串可能含 token，僅保留路徑。
            "path": request.url.path,
        }
        _enqueue_record(record)
    except Exception:
        _warn("Audit recording failed; request continues")


def _capture_metadata(kwargs: dict, value=None) -> None:
    try:
        _capture_metadata_fields(kwargs, value)
    except Exception:
        _warn("Audit metadata observation failed")


def _capture_metadata_fields(kwargs: dict, value=None) -> None:
    request = _request_context.get()
    if request is None:
        return
    for name in ("auth", "_auth", "auth_info"):
        auth = kwargs.get(name)
        if isinstance(auth, dict):
            actor = dict(getattr(request.state, "audit_actor", {}))
            actor.update(auth)
            request.state.audit_actor = actor
    target = dict(getattr(request.state, "audit_target", {}))
    # 只取明確可公開的識別欄位，絕不序列化整個 body 或 response。
    sources = [kwargs, value]
    sources.extend(
        source for name, source in kwargs.items()
        if name not in {"auth", "_auth", "auth_info"}
    )
    for source in sources:
        if isinstance(source, Request):
            continue
        for field in _TARGET_FIELDS:
            item = source.get(field) if isinstance(source, dict) else getattr(
                source, field, None,
            )
            if isinstance(item, (str, bool, int)):
                target[field] = _text(item) if isinstance(item, str) else item
            elif isinstance(item, list) and all(
                isinstance(entry, str) for entry in item
            ):
                target[field] = [_text(entry) for entry in item]
        files = getattr(source, "files", None)
        if isinstance(files, list):
            target["filenames"] = [
                _text(item.filename) for item in files
                if isinstance(getattr(item, "filename", None), str)
            ]
        if isinstance(source, dict) and isinstance(source.get("prompt"), dict):
            target.update(_safe_target(source["prompt"]))
    request.state.audit_target = target
    if getattr(request.state, "audit_action", None) == "auth.login":
        body = kwargs.get("body")
        if body is not None:
            observe_actor(request, username=body.username,
                          auth_method="anonymous")
        if isinstance(value, dict) and "role" in value:
            observe_actor(request, role=value["role"], auth_method="session")


def _observe_metadata(kwargs: dict, value=None) -> None:
    try:
        _capture_metadata(kwargs, value)
    except Exception:
        _warn("Audit metadata observation failed")


def _observe_outcome(request: Request, action: str, status: int, exc) -> None:
    try:
        if exc is not None:
            status = getattr(exc, "status_code", 500)
        reason = getattr(request.state, "audit_reason", None)
        if isinstance(exc, RequestValidationError):
            status = 422
            reason = "validation_error"
            if action == "auth.login" and isinstance(exc.body, dict):
                observe_actor(request, username=_text(exc.body.get("username")),
                              auth_method="anonymous")
        if action == "auth.login" and status == 401 and reason is None:
            reason = "credentials_rejected"
        if action == "rag.reindex" and status < 400:
            reason = "accepted"
        target = {
            key: _text(value) for key, value in request.path_params.items()
            if isinstance(value, str)
        }
        target.update(getattr(request.state, "audit_target", {}))
        record_audit(
            request, action, "success" if status < 400 else "failure",
            reason=reason or (f"http_{status}" if status >= 400 else None),
            target=target,
        )
    except Exception:
        _warn("Audit outcome observation failed; request continues")


class AuditRoute(APIRoute):
    """Capture outcomes including dependency and request-validation failures."""

    def __init__(self, path, endpoint, **kwargs):
        from app.services.audit_actions import resolve_action

        if not any(resolve_action(endpoint.__module__, endpoint.__name__, method)
                   for method in (kwargs.get("methods") or {"GET"})):
            super().__init__(path, endpoint, **kwargs)
            return
        if getattr(endpoint, "_audit_wrapped", False):
            super().__init__(path, endpoint, **kwargs)
            return
        if inspect.iscoroutinefunction(endpoint):
            @wraps(endpoint)
            async def wrapped(*args, **values):
                _observe_metadata(values)
                result = await endpoint(*args, **values)
                _observe_metadata({}, result)
                return result
        else:
            @wraps(endpoint)
            def wrapped(*args, **values):
                _observe_metadata(values)
                result = endpoint(*args, **values)
                _observe_metadata({}, result)
                return result
        wrapped.__signature__ = inspect.signature(endpoint, eval_str=True)
        wrapped._audit_wrapped = True
        super().__init__(path, wrapped, **kwargs)

    def get_route_handler(self):
        from app.services.audit_actions import resolve_action

        handler = super().get_route_handler()
        action = resolve_action(
            self.endpoint.__module__, self.endpoint.__name__,
            next(iter(self.methods - {"HEAD"}), "GET"),
        )
        if not action:
            return handler

        async def audited(request: Request):
            context = None
            try:
                context = _request_context.set(request)
                request.state.audit_action = action
            except Exception:
                _warn("Audit request observation unavailable")
                if context is not None:
                    try:
                        _request_context.reset(context)
                    except Exception:
                        _warn("Audit request context cleanup failed")
                return await handler(request)
            status = 500
            error = None
            try:
                response = await handler(request)
                try:
                    status = response.status_code
                except Exception:
                    _warn("Audit response metadata unavailable")
                return response
            except Exception as exc:
                error = exc
                raise
            finally:
                try:
                    _observe_outcome(request, action, status, error)
                except Exception:
                    _warn("Audit outcome observation unavailable")
                finally:
                    try:
                        _request_context.reset(context)
                    except Exception:
                        _warn("Audit request context cleanup failed")

        return audited
