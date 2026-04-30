"""Compatibility endpoints for the generic homepage knowledge-store UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import require_admin, verify_auth
from app.services import gemini_clients
from app.services.hciot.knowledge_store import get_hciot_knowledge_store
from app.services.jti.knowledge_store import get_jti_knowledge_store

router = APIRouter(prefix="/api", tags=["Store Management"])


@dataclass(frozen=True)
class ManagedStoreConfig:
    name: str
    display_name: str
    managed_app: str
    managed_language: str
    key_keyword: str = ""


class CreateStoreRequest(BaseModel):
    display_name: str
    key_index: int = 0


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


def resolve_key_index_for_store(store_name: str) -> int:
    """Return the Gemini key index for a managed store by matching its keyword against key names."""
    config = resolve_managed_store(store_name)
    if config and config.key_keyword:
        return gemini_clients.resolve_key_index_by_keyword(config.key_keyword)
    return 0


def _knowledge_store_for(config: ManagedStoreConfig):
    if config.managed_app == "hciot":
        return get_hciot_knowledge_store()
    return get_jti_knowledge_store()


def _list_store_files(config: ManagedStoreConfig) -> list[dict[str, Any]]:
    try:
        return list(_knowledge_store_for(config).list_files(config.managed_language))
    except Exception:
        return []


def _store_payload(config: ManagedStoreConfig) -> dict[str, Any]:
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


@router.get("/stores")
def list_stores(auth: dict = Depends(verify_auth)):
    """Return fixed local knowledge stores used by the generic homepage."""
    require_admin(auth)
    return [_store_payload(config) for config in MANAGED_STORES]


@router.get("/keys/count")
def get_keys_count(auth: dict = Depends(verify_auth)):
    """Return configured Gemini API key count and display names."""
    require_admin(auth)
    return {
        "count": gemini_clients.get_key_count(),
        "names": gemini_clients.get_key_names(),
    }


@router.post("/stores")
def create_store(_: CreateStoreRequest, auth: dict = Depends(verify_auth)):
    """Legacy create-store route kept to return a clear error instead of 404."""
    require_admin(auth)
    raise HTTPException(
        status_code=400,
        detail="This deployment uses fixed local knowledge stores. Add content from the JTI/HCIoT knowledge management pages.",
    )


@router.get("/stores/{store_name:path}/files")
def list_files(store_name: str, auth: dict = Depends(verify_auth)):
    """List files for a managed local knowledge store."""
    require_admin(auth)
    config = resolve_managed_store(store_name)
    if config is None:
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    return _list_store_files(config)


@router.delete("/stores/{store_name:path}")
def delete_store(store_name: str, auth: dict = Depends(verify_auth)):
    """Legacy delete-store route kept to return a clear error instead of 404."""
    require_admin(auth)
    if resolve_managed_store(store_name) is None:
        raise HTTPException(status_code=404, detail="Knowledge store not found")
    raise HTTPException(status_code=400, detail="Managed knowledge stores cannot be deleted")
