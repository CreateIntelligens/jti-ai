"""Compatibility endpoints for the generic homepage knowledge-store UI."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.auth import extract_user_gemini_api_key, require_admin, verify_auth
import app.deps as deps
from app.routers.knowledge_utils import delete_from_rag, safe_filename, sync_to_rag
from app.services import gemini_clients
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
    key_keyword: str = ""
    key_index: int | None = None


class CreateStoreRequest(BaseModel):
    display_name: str
    key_index: int = 0


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

    def list_stores(self, owner_key_hash: str | None = None) -> list[dict[str, Any]]:
        query = self._owner_filter(owner_key_hash)
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
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        doc = {
            "name": self._new_store_name(),
            "display_name": display_name.strip(),
            "key_index": None if owner_key_hash else int(key_index),
            "owner_key_hash": owner_key_hash,
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
    ManagedStoreConfig("__jti__", "JTI 中文", "jti", "zh", key_keyword="JTI"),
    ManagedStoreConfig("__jti__en", "JTI English", "jti", "en", key_keyword="JTI"),
    ManagedStoreConfig("__hciot__", "HCIoT 中文", "hciot", "zh", key_keyword="HCIOT"),
    ManagedStoreConfig("__hciot__en", "HCIoT English", "hciot", "en", key_keyword="HCIOT"),
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
        managed_app="",
        managed_language="",
        key_index=dynamic.get("key_index"),
    )


def resolve_key_index_for_store(store_name: str) -> int:
    """Return the Gemini key index for a managed or user-created store."""
    config = resolve_managed_store(store_name)
    if config and config.key_keyword:
        return gemini_clients.resolve_key_index_by_keyword(config.key_keyword)
    dynamic = get_store_registry().get_store(normalize_store_name(store_name))
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


def _dynamic_store_payload(store: dict[str, Any]) -> dict[str, Any]:
    store_name = store["name"]
    return {
        "name": store_name,
        "display_name": store.get("display_name") or store_name,
        "file_count": len(_list_general_store_files(store_name)),
        "created_at": store.get("created_at"),
        "managed_app": None,
        "managed_language": None,
        "key_index": store.get("key_index"),
    }


@router.get("/stores")
def list_stores(request: Request, auth: dict = Depends(verify_auth)):
    """Return fixed app stores plus key-owned general homepage stores."""
    require_admin(auth)
    owner_hash = _owner_key_hash(request)
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
    store = get_store_registry().create_store(
        display_name=display_name,
        key_index=key_index,
        owner_key_hash=owner_hash,
    )
    return _dynamic_store_payload(store)


@router.get("/stores/{store_name}/files")
def list_files(store_name: str, request: Request, auth: dict = Depends(verify_auth)):
    """List files for a fixed managed store or a general key-owned store."""
    require_admin(auth)
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
    require_admin(auth)
    if resolve_managed_store(store_name) is not None:
        raise HTTPException(status_code=400, detail="Managed stores use their app-specific knowledge pages")

    normalized = normalize_store_name(store_name)
    if not get_store_registry().get_store(normalized, _owner_key_hash(request)):
        raise HTTPException(status_code=404, detail="Knowledge store not found")

    display_name = file.filename or f"file_{uuid.uuid4().hex[:8]}"
    safe_name = safe_filename(display_name)
    file_bytes = await file.read()
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
    require_admin(auth)
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
