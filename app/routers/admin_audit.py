"""Read security action records with restricted access."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import verify_auth
from app.services.audit_log import AuditRoute, get_audit_collection

router = APIRouter(
    prefix="/api/admin", tags=["Audit Logs"], route_class=AuditRoute,
)


def require_super_admin(auth: dict = Depends(verify_auth)) -> dict:
    if auth.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Insufficient role")
    return auth


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.get("/audit-logs")
def list_audit_logs(
    action: str | None = None,
    user_id: str | None = None,
    username: str | None = None,
    client_ip: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=100, ge=1),
    offset: int = Query(default=0, ge=0),
    _auth: dict = Depends(require_super_admin),
):
    query = {}
    for field, value in (
        ("action", action), ("actor.user_id", user_id),
        ("actor.username", username), ("client_ip", client_ip),
    ):
        if value is not None:
            query[field] = value
    if since and until and _utc(since) > _utc(until):
        raise HTTPException(status_code=422, detail="Invalid time range")
    if since or until:
        query["timestamp"] = {}
        if since:
            query["timestamp"]["$gte"] = _utc(since)
        if until:
            query["timestamp"]["$lte"] = _utc(until)
    limit = min(limit, 500)
    collection = get_audit_collection()
    items = list(
        collection.find(query, {"_id": 0}).sort("timestamp", -1)
        .skip(offset).limit(limit)
    )
    for item in items:
        item.pop("_id", None)
    return {
        "items": items, "total": collection.count_documents(query),
        "limit": limit, "offset": offset,
    }
