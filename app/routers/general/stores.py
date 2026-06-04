"""Compatibility endpoints for the generic homepage knowledge-store UI."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.auth import extract_user_gemini_api_key, require_admin, verify_auth
import app.deps as deps
from app.routers.knowledge_utils import (
    EDITABLE_EXTENSIONS,
    TEXT_PREVIEW_EXTENSIONS,
    delete_from_rag,
    extract_docx_text,
    safe_filename,
    sync_to_rag,
    write_docx_text,
    check_upload_rate_limit,
    validate_upload_limits,
)
from app.services import app_key_map, gemini_clients
from app.services.hciot.knowledge_store import get_hciot_knowledge_store
from app.services.jti.knowledge_store import get_jti_knowledge_store
from app.services.knowledge_store import get_knowledge_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Store Management"])


@dataclass(frozen=True)
class ManagedStoreConfig:
    name: str
    display_name: str
    managed_app: str
    managed_language: str
    key_index: int | None = None
    key_name: str | None = None


class CreateStoreRequest(BaseModel):
    display_name: str
    key_index: int = 0


class UpdateFileContentRequest(BaseModel):
    content: str


GENERAL_NAMESPACE = "general"


class StoreRegistry:
    """Mongo-backed metadata for user-created homepage knowledge stores."""

    COLLECTION_NAME = "knowledge_stores"

    def __init__(self, db_name: str = "jti_app") -> None:
        from app.services.mongo_client import get_mongo_db

        self.collection = get_mongo_db(db_name)[self.COLLECTION_NAME]
        try:
            self.collection.create_index("name", unique=True)
            self.collection.create_index("key_index")
            self.collection.create_index("owner_key_hash")
            self.collection.create_index([("created_at", -1)])
        except Exception as exc:
            logger.warning("Store registry index creation failed: %s", exc)

    @staticmethod
    def _payload(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": doc.get("name"),
            "display_name": doc.get("display_name") or doc.get("name"),
            "key_index": doc.get("key_index"),
            "created_at": doc.get("created_at"),
            "owner_key_hash": doc.get("owner_key_hash"),
            "managed_app": doc.get("managed_app") or "general",
            "key_name": doc.get("key_name"),
        }

    @staticmethod
    def _new_store_name() -> str:
        return f"store_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _owner_filter(owner_key_hash: str | None) -> dict[str, Any]:
        if owner_key_hash:
            return {"owner_key_hash": owner_key_hash}
        return {
            "$or": [
                {"owner_key_hash": {"$exists": False}},
                {"owner_key_hash": None},
            ]
        }

    @staticmethod
    def _app_filter(app: str | None) -> dict[str, Any]:
        normalized = (app or "").strip().lower()
        if not normalized:
            return {}
        if normalized == "general":
            return {
                "$or": [
                    {"managed_app": "general"},
                    {"managed_app": {"$exists": False}},
                    {"managed_app": None},
                ]
            }
        return {"managed_app": normalized}

    @staticmethod
    def _merge_filters(*filters: dict[str, Any]) -> dict[str, Any]:
        active_filters = [item for item in filters if item]
        if not active_filters:
            return {}
        if len(active_filters) == 1:
            return active_filters[0]
        return {"$and": active_filters}

    def list_stores(
        self,
        owner_key_hash: str | None = None,
        app: str | None = None,
    ) -> list[dict[str, Any]]:
        query = self._merge_filters(
            self._owner_filter(owner_key_hash),
            self._app_filter(app),
        )
        try:
            docs = self.collection.find(query, {"_id": 0}).sort("created_at", 1)
            return [self._payload(doc) for doc in docs]
        except Exception as exc:
            logger.warning("Failed to list dynamic stores: %s", exc)
            return []

    def create_store(
        self,
        display_name: str,
        key_index: int = 0,
        owner_key_hash: str | None = None,
        managed_app: str | None = None,
        key_name: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        key_names = gemini_clients.get_key_names()
        if key_name is None and not owner_key_hash and 0 <= int(key_index) < len(key_names):
            key_name = key_names[int(key_index)]
        if managed_app is not None:
            resolved_app = managed_app
        elif owner_key_hash:
            resolved_app = "general"
        elif key_name:
            resolved_app = app_key_map.resolve_app_for_key_name(key_name)
        else:
            resolved_app = app_key_map.resolve_app_for_key_index(int(key_index))
        resolved_app = resolved_app.strip().lower() or "general"
        doc = {
            "name": self._new_store_name(),
            "display_name": display_name.strip(),
            "key_index": None if owner_key_hash else int(key_index),
            "key_name": None if owner_key_hash else key_name,
            "owner_key_hash": owner_key_hash,
            "managed_app": resolved_app,
            "created_at": now,
            "updated_at": now,
        }
        self.collection.insert_one(doc)
        return self._payload(doc)

    def get_store(self, store_name: str, owner_key_hash: str | None = None) -> dict[str, Any] | None:
        query = {"name": store_name, **self._owner_filter(owner_key_hash)}
        doc = self.collection.find_one(query, {"_id": 0})
        return self._payload(doc) if doc else None

    def delete_store(self, store_name: str, owner_key_hash: str | None = None) -> bool:
        query = {"name": store_name, **self._owner_filter(owner_key_hash)}
        result = self.collection.delete_one(query)
        return result.deleted_count > 0


_store_registry: StoreRegistry | None = None


def get_store_registry() -> StoreRegistry:
    global _store_registry
    if _store_registry is None:
        _store_registry = StoreRegistry()
    return _store_registry


MANAGED_STORES: tuple[ManagedStoreConfig, ...] = (
    ManagedStoreConfig("__jti__", "JTI 中文", "jti", "zh"),
    ManagedStoreConfig("__jti__en", "JTI English", "jti", "en"),
    ManagedStoreConfig("__hciot__", "HCIoT 中文", "hciot", "zh"),
    ManagedStoreConfig("__hciot__en", "HCIoT English", "hciot", "en"),
)

_STORE_ALIASES: dict[str, str] = {
    "jti": "__jti__",
    "jti-zh": "__jti__",
    "jti_zh": "__jti__",
    "jti-en": "__jti__en",
    "jti_en": "__jti__en",
    "hciot": "__hciot__",
    "hciot-zh": "__hciot__",
    "hciot_zh": "__hciot__",
    "hciot-en": "__hciot__en",
    "hciot_en": "__hciot__en",
}


def normalize_store_name(store_name: str | None) -> str:
    normalized = (store_name or "").strip()
    if not normalized:
        return "__jti__"
    return _STORE_ALIASES.get(normalized.lower(), normalized)


def resolve_managed_store(store_name: str | None) -> ManagedStoreConfig | None:
    normalized = normalize_store_name(store_name)
    return next((store for store in MANAGED_STORES if store.name == normalized), None)


def resolve_store_config(store_name: str | None, owner_key_hash: str | None = None) -> ManagedStoreConfig | None:
    managed = resolve_managed_store(store_name)
    if managed is not None:
        return managed

    normalized = normalize_store_name(store_name)
    dynamic = get_store_registry().get_store(normalized, owner_key_hash)
    if not dynamic:
        return None
    return ManagedStoreConfig(
        name=dynamic["name"],
        display_name=dynamic.get("display_name") or dynamic["name"],
        managed_app=dynamic.get("managed_app", "general"),
        managed_language="",
        key_index=dynamic.get("key_index"),
        key_name=dynamic.get("key_name"),
    )


def resolve_key_index_for_store(store_name: str) -> int:
    """Return the Gemini key index for a managed or user-created store."""
    config = resolve_managed_store(store_name)
    if config is not None:
        idx = app_key_map.resolve_key_index_for_app(config.managed_app)
        if idx < 0:
            # 找不到對應 key:明確告警,不靜默用第一把 key(避免用錯 key 還不報錯)。
            logger.warning(
                "[stores] managed_app=%s 無法從 APP_KEY_MAP 解析 Gemini key;"
                "請檢查 APP_KEY_MAP 與 GEMINI_API_KEYS。退回 index 0。",
                config.managed_app,
            )
            return 0
        return idx
    dynamic = get_store_registry().get_store(normalize_store_name(store_name))
    if dynamic and dynamic.get("key_name"):
        idx = gemini_clients.resolve_key_index_by_name(str(dynamic["key_name"]))
        if idx >= 0:
            return idx
    if dynamic and isinstance(dynamic.get("key_index"), int):
        return int(dynamic["key_index"])
    return 0


def hash_user_gemini_api_key(api_key: str | None) -> str | None:
    normalized = (api_key or "").strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _owner_key_hash(request: Request) -> str | None:
    return hash_user_gemini_api_key(extract_user_gemini_api_key(request))


def _validate_store_name(display_name: str) -> str:
    normalized = (display_name or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Knowledge store name is required")
    return normalized


def _validate_key_index(key_index: int, owner_key_hash: str | None) -> int:
    if owner_key_hash:
        return int(key_index)
    if key_index < 0:
        raise HTTPException(status_code=400, detail="key_index must be non-negative")
    key_count = gemini_clients.get_key_count()
    if key_count and key_index >= key_count:
        raise HTTPException(status_code=400, detail="Selected Gemini key does not exist")
    return int(key_index)


def _knowledge_store_for(config: ManagedStoreConfig):
    if config.managed_app == "hciot":
        return get_hciot_knowledge_store()
    return get_jti_knowledge_store()


def _list_store_files(config: ManagedStoreConfig) -> list[dict[str, Any]]:
    try:
        return list(_knowledge_store_for(config).list_files(config.managed_language))
    except Exception:
        return []


def _list_general_store_files(store_name: str) -> list[dict[str, Any]]:
    try:
        return list(get_knowledge_store().list_files(store_name, namespace=GENERAL_NAMESPACE))
    except Exception:
        return []


def _managed_store_payload(config: ManagedStoreConfig) -> dict[str, Any]:
    files = _list_store_files(config)
    return {
        "name": config.name,
        "display_name": config.display_name,
        "file_count": len(files),
        "created_at": None,
        "managed_app": config.managed_app,
        "managed_language": config.managed_language,
        "key_index": resolve_key_index_for_store(config.name),
    }


def _normalize_key_name(name: str | None) -> str:
    return (name or "").strip().lower()


def _key_name_for_store(store: dict[str, Any]) -> str | None:
    key_name = store.get("key_name")
    if isinstance(key_name, str) and key_name.strip():
        return key_name.strip()
    key_index = store.get("key_index")
    if isinstance(key_index, int):
        key_names = gemini_clients.get_key_names()
        if 0 <= key_index < len(key_names):
            return key_names[key_index]
    return None


def _key_index_for_store_payload(store: dict[str, Any], key_name: str | None) -> int | None:
    if key_name:
        resolved = gemini_clients.resolve_key_index_by_name(key_name)
        if resolved >= 0:
            return resolved
    key_index = store.get("key_index")
    return key_index if isinstance(key_index, int) else None


def _dynamic_store_payload(store: dict[str, Any]) -> dict[str, Any]:
    store_name = store["name"]
    key_name = _key_name_for_store(store)
    return {
        "name": store_name,
        "display_name": store.get("display_name") or store_name,
        "file_count": len(_list_general_store_files(store_name)),
        "created_at": store.get("created_at"),
        "managed_app": store.get("managed_app") or "general",
        "managed_language": None,
        "key_index": _key_index_for_store_payload(store, key_name),
        "key_name": key_name,
    }


def _normalize_app_filter(app: str | None) -> str | None:
    normalized = (app or "").strip().lower()
    return normalized or None


def _key_name_from_scope(scope: str | None) -> str | None:
    normalized = _normalize_app_filter(scope)
    if normalized is None:
        return None
    if normalized.startswith("key:"):
        raise HTTPException(status_code=400, detail="Key scopes must use key_name:<name>")
    if not normalized.startswith("key_name:"):
        return None
    raw_name = normalized.removeprefix("key_name:")
    key_name = unquote(raw_name).strip()
    if not key_name:
        raise HTTPException(status_code=400, detail="Invalid key scope")
    return key_name


def _dynamic_store_matches_scope(store: dict[str, Any], scope: str | None) -> bool:
    normalized = _normalize_app_filter(scope)
    if normalized is None:
        return True
    key_name = _key_name_from_scope(normalized)
    if key_name is not None:
        return _normalize_key_name(_key_name_for_store(store)) == _normalize_key_name(key_name)
    return (store.get("managed_app") or "general").strip().lower() == normalized


def store_config_matches_scope(config: ManagedStoreConfig, scope: str | None) -> bool:
    """Return whether a resolved store belongs to an app or registered-key scope."""
    normalized = _normalize_app_filter(scope)
    if normalized is None:
        return True
    key_name = _key_name_from_scope(normalized)
    if key_name is not None:
        return _normalize_key_name(config.key_name) == _normalize_key_name(key_name)
    return bool(config.managed_app) and config.managed_app.lower() == normalized


def _list_key_name_scoped_store_payloads(
    owner_key_hash: str | None,
    key_name: str,
) -> list[dict[str, Any]]:
    return [
        _dynamic_store_payload(store)
        for store in get_store_registry().list_stores(owner_key_hash)
        if _dynamic_store_matches_scope(store, f"key_name:{key_name}")
    ]


def _list_app_scoped_store_payloads(owner_key_hash: str | None, app: str) -> list[dict[str, Any]]:
    managed = [
        _managed_store_payload(config)
        for config in MANAGED_STORES
        if config.managed_app == app
    ]
    dynamic = [
        _dynamic_store_payload(store)
        for store in get_store_registry().list_stores(owner_key_hash, app=app)
    ]
    return managed + dynamic


def _list_scope_scoped_store_payloads(
    owner_key_hash: str | None,
    scope: str,
) -> list[dict[str, Any]]:
    key_name = _key_name_from_scope(scope)
    if key_name is not None:
        return _list_key_name_scoped_store_payloads(owner_key_hash, key_name)
    return _list_app_scoped_store_payloads(owner_key_hash, scope)


def _scope_values_equal(left: str | None, right: str | None) -> bool:
    normalized_left = _normalize_app_filter(left)
    normalized_right = _normalize_app_filter(right)
    left_key_name = _key_name_from_scope(normalized_left)
    right_key_name = _key_name_from_scope(normalized_right)
    if left_key_name is not None or right_key_name is not None:
        return _normalize_key_name(left_key_name) == _normalize_key_name(right_key_name)
    return normalized_left == normalized_right


def _list_assigned_store_payloads(
    store_name: str,
    owner_key_hash: str | None,
    app_filter: str | None,
    auth_scope: str | None = None,
) -> list[dict[str, Any]]:
    expected_scope = _normalize_app_filter(auth_scope)
    managed = resolve_managed_store(store_name)
    if managed is not None:
        if expected_scope is not None and not store_config_matches_scope(managed, expected_scope):
            raise HTTPException(status_code=403, detail="Access denied")
        if app_filter is not None and not store_config_matches_scope(managed, app_filter):
            raise HTTPException(status_code=403, detail="Access denied")
        return [_managed_store_payload(managed)]

    normalized = normalize_store_name(store_name)
    dynamic = get_store_registry().get_store(normalized, owner_key_hash)
    if dynamic is None:
        raise HTTPException(status_code=404, detail="Knowledge store not found")

    if expected_scope is not None and not _dynamic_store_matches_scope(dynamic, expected_scope):
        raise HTTPException(status_code=403, detail="Access denied")
    if app_filter is not None and not _dynamic_store_matches_scope(dynamic, app_filter):
        raise HTTPException(status_code=403, detail="Access denied")
    return [_dynamic_store_payload(dynamic)]


def _list_user_scoped_stores(
    auth: dict,
    owner_key_hash: str | None,
    app_filter: str | None,
) -> list[dict[str, Any]]:
    assigned_store = (auth.get("store_name") or "").strip()
    if assigned_store:
        return _list_assigned_store_payloads(
            assigned_store,
            owner_key_hash,
            app_filter,
            auth.get("scope"),
        )

    auth_scope = (auth.get("scope") or "").strip().lower()
    if not auth_scope:
        raise HTTPException(status_code=403, detail="Access denied")
    if app_filter is not None and not _scope_values_equal(app_filter, auth_scope):
        raise HTTPException(status_code=403, detail="Access denied")
    return _list_scope_scoped_store_payloads(owner_key_hash, auth_scope)


@router.get("/stores")
def list_stores(
    request: Request,
    app: str | None = None,
    auth: dict = Depends(verify_auth),
):
    """Return fixed app stores plus key-owned general homepage stores."""
    app_filter = _normalize_app_filter(app)
    owner_hash = _owner_key_hash(request)
    if auth.get("role") == "user":
        return _list_user_scoped_stores(auth, owner_hash, app_filter)

    require_admin(auth)
    if app_filter is not None:
        return _list_scope_scoped_store_payloads(owner_hash, app_filter)
    managed = [_managed_store_payload(config) for config in MANAGED_STORES]
    dynamic = [_dynamic_store_payload(store) for store in get_store_registry().list_stores(owner_hash)]
    return managed + dynamic


@router.get("/keys/count")
def get_keys_count(auth: dict = Depends(verify_auth)):
    """Return configured Gemini API key count and display names."""
    require_admin(auth)
    return {
        "count": gemini_clients.get_key_count(),
        "names": gemini_clients.get_key_names(),
    }


@router.post("/stores")
def create_store(request_data: CreateStoreRequest, request: Request, auth: dict = Depends(verify_auth)):
    """Create a general homepage knowledge store bound to the selected Gemini key."""
    require_admin(auth)
    display_name = _validate_store_name(request_data.display_name)
    owner_hash = _owner_key_hash(request)
    key_index = _validate_key_index(request_data.key_index, owner_hash)
    key_names = gemini_clients.get_key_names()
    key_name = key_names[key_index] if not owner_hash and 0 <= key_index < len(key_names) else None
    store = get_store_registry().create_store(
        display_name=display_name,
        key_index=key_index,
        owner_key_hash=owner_hash,
        key_name=key_name,
    )
    return _dynamic_store_payload(store)


def _authorize_store_access(store_name: str, request: Request, auth: dict) -> None:
    """Authorize read or content-mutation access to a general key-owned store.

    Admins/super_admins pass unconditionally. A key-bound user (sk-xxx) may access
    only the store its key is bound to — read AND content edits (upload/delete/update)
    are consistent: if the key can see the store, it can manage its contents. Deleting
    the store itself stays admin-only (handled separately). Mirrors the chat store
    resolver scope check to avoid cross-app IDOR."""
    if auth.get("role") in {"admin", "super_admin"}:
        return

    assigned_store = auth.get("store_name")
    if assigned_store:
        if normalize_store_name(assigned_store) != normalize_store_name(store_name):
            raise HTTPException(status_code=403, detail="Access denied")
        return

    config = resolve_store_config(store_name, _owner_key_hash(request))
    if config is None:
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    if not store_config_matches_scope(config, auth.get("scope")):
        raise HTTPException(status_code=403, detail="Access denied")


@router.get("/stores/{store_name}/files")
def list_files(store_name: str, request: Request, auth: dict = Depends(verify_auth)):
    """List files for a fixed managed store or a general key-owned store."""
    _authorize_store_access(store_name, request, auth)
    config = resolve_managed_store(store_name)
    if config is not None:
        return _list_store_files(config)

    normalized = normalize_store_name(store_name)
    if not get_store_registry().get_store(normalized, _owner_key_hash(request)):
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    return _list_general_store_files(normalized)


@router.post("/stores/{store_name}/files")
async def upload_file(
    store_name: str,
    request: Request,
    file: UploadFile = File(...),
    auth: dict = Depends(verify_auth),
):
    """Upload a file into a general key-owned knowledge store."""
    check_upload_rate_limit(request)
    _authorize_store_access(store_name, request, auth)
    if resolve_managed_store(store_name) is not None:
        raise HTTPException(status_code=400, detail="Managed stores use their app-specific knowledge pages")

    normalized = normalize_store_name(store_name)
    if not get_store_registry().get_store(normalized, _owner_key_hash(request)):
        raise HTTPException(status_code=404, detail="Knowledge store not found")

    display_name = file.filename or f"file_{uuid.uuid4().hex[:8]}"
    safe_name = safe_filename(display_name)
    file_bytes = await file.read()

    # Validate file size, count, and total store storage limit
    files = _list_general_store_files(normalized)
    validate_upload_limits(files, safe_name, file_bytes)

    content_type = file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    saved = get_knowledge_store().insert_file(
        language=normalized,
        filename=safe_name,
        data=file_bytes,
        display_name=safe_name,
        content_type=content_type,
        editable=True,
        namespace=GENERAL_NAMESPACE,
    )

    rag_synced = False
    try:
        sync_to_rag(GENERAL_NAMESPACE, normalized, saved["name"], file_bytes)
        rag_synced = True
    except Exception as exc:
        logger.warning("[Knowledge] RAG sync failed for %s/%s: %s", normalized, saved["name"], exc)

    return {
        **saved,
        "synced": rag_synced,
    }


@router.delete("/stores/{store_name}/files/{filename:path}")
def delete_file(store_name: str, filename: str, request: Request, auth: dict = Depends(verify_auth)):
    """Delete a file from a general key-owned knowledge store."""
    _authorize_store_access(store_name, request, auth)
    if resolve_managed_store(store_name) is not None:
        raise HTTPException(status_code=400, detail="Managed stores use their app-specific knowledge pages")

    normalized = normalize_store_name(store_name)
    if not get_store_registry().get_store(normalized, _owner_key_hash(request)):
        raise HTTPException(status_code=404, detail="Knowledge store not found")

    safe_name = safe_filename(filename)
    store = get_knowledge_store()
    if store.get_file_data(normalized, safe_name, namespace=GENERAL_NAMESPACE) is None:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        delete_from_rag(GENERAL_NAMESPACE, normalized, safe_name)
    except Exception as exc:
        logger.warning("[Knowledge] RAG delete failed for %s/%s: %s", normalized, safe_name, exc)

    deleted = store.delete_file(normalized, safe_name, namespace=GENERAL_NAMESPACE)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")
    return {"message": "File deleted"}


@router.get("/stores/{store_name}/files/{filename:path}/content")
def get_store_file_content(
    store_name: str,
    filename: str,
    request: Request,
    auth: dict = Depends(verify_auth),
):
    """Return text content of a file for inline preview/edit."""
    _authorize_store_access(store_name, request, auth)
    if resolve_managed_store(store_name) is not None:
        raise HTTPException(
            status_code=400,
            detail="Managed stores expose content via their app-specific routes (e.g. /api/hciot/knowledge or /api/jti/knowledge)",
        )

    normalized = normalize_store_name(store_name)
    if not get_store_registry().get_store(normalized, _owner_key_hash(request)):
        raise HTTPException(status_code=404, detail="Knowledge store not found")

    safe_name = safe_filename(filename)
    store = get_knowledge_store()
    doc = store.get_file(normalized, safe_name, namespace=GENERAL_NAMESPACE)
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")

    file_bytes: bytes = doc.get("data", b"")
    ext = (
        "." + safe_name.rsplit(".", 1)[-1].lower()
        if "." in safe_name
        else ""
    )

    if ext == ".docx":
        return {
            "filename": safe_name,
            "editable": True,
            "content": extract_docx_text(file_bytes),
            "size": doc.get("size", len(file_bytes)),
        }

    if ext not in TEXT_PREVIEW_EXTENSIONS:
        return {
            "filename": safe_name,
            "editable": False,
            "content": None,
            "message": "此檔案格式不支援線上預覽，請下載查看",
        }

    return {
        "filename": safe_name,
        "editable": ext in EDITABLE_EXTENSIONS,
        "content": file_bytes.decode("utf-8", errors="replace"),
        "size": doc.get("size", len(file_bytes)),
    }


@router.put("/stores/{store_name}/files/{filename:path}/content")
async def update_store_file_content(
    store_name: str,
    filename: str,
    req: UpdateFileContentRequest,
    request: Request,
    auth: dict = Depends(verify_auth),
):
    """Save edited text content and re-index the file in RAG."""
    _authorize_store_access(store_name, request, auth)
    if resolve_managed_store(store_name) is not None:
        raise HTTPException(
            status_code=400,
            detail="Managed stores expose content via their app-specific routes (e.g. /api/hciot/knowledge or /api/jti/knowledge)",
        )

    normalized = normalize_store_name(store_name)
    if not get_store_registry().get_store(normalized, _owner_key_hash(request)):
        raise HTTPException(status_code=404, detail="Knowledge store not found")

    safe_name = safe_filename(filename)
    ext = (
        "." + safe_name.rsplit(".", 1)[-1].lower()
        if "." in safe_name
        else ""
    )
    if ext not in EDITABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="此檔案格式不支援線上編輯")

    store = get_knowledge_store()
    doc = store.get_file(normalized, safe_name, namespace=GENERAL_NAMESPACE)
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")

    if ext == ".docx":
        try:
            new_bytes = write_docx_text(doc.get("data", b""), req.content)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"寫入 docx 失敗: {exc}")
    else:
        new_bytes = req.content.encode("utf-8")

    updated = store.update_file_content(
        normalized, safe_name, new_bytes, namespace=GENERAL_NAMESPACE
    )
    if not updated:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        sync_to_rag(GENERAL_NAMESPACE, normalized, safe_name, new_bytes)
    except Exception as exc:
        logger.warning(
            "[Knowledge] RAG sync failed for %s/%s: %s", normalized, safe_name, exc
        )
        return {"message": "已更新，但 RAG 同步失敗", "synced": False}

    return {"message": "已更新", "synced": True}


@router.delete("/stores/{store_name:path}")
def delete_store(store_name: str, request: Request, auth: dict = Depends(verify_auth)):
    """Delete a general key-owned store and its files."""
    require_admin(auth)
    if resolve_managed_store(store_name) is not None:
        raise HTTPException(status_code=400, detail="Managed knowledge stores cannot be deleted")

    normalized = normalize_store_name(store_name)
    owner_hash = _owner_key_hash(request)
    if not get_store_registry().get_store(normalized, owner_hash):
        raise HTTPException(status_code=404, detail="Knowledge store not found")

    for file_info in _list_general_store_files(normalized):
        filename = file_info.get("filename") or file_info.get("name")
        if not filename:
            continue
        try:
            delete_from_rag(GENERAL_NAMESPACE, normalized, filename)
        except Exception as exc:
            logger.warning("[Knowledge] RAG delete failed for %s/%s: %s", normalized, filename, exc)

    get_knowledge_store().delete_by_namespace(GENERAL_NAMESPACE, language=normalized)
    if deps.prompt_manager:
        deps.prompt_manager.delete_store_prompts(normalized)
    if deps.api_key_manager:
        deps.api_key_manager.delete_store_keys(normalized)
    get_store_registry().delete_store(normalized, owner_hash)
    return {"message": "Knowledge store deleted"}
