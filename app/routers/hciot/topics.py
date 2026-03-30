"""
HCIoT Topics public API.

Returns the full category → topic → questions hierarchy for the frontend.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import verify_auth
from app.services.hciot.topic_store import get_hciot_topic_store

router = APIRouter(tags=["HCIoT Topics"])


@router.get("/topics")
def list_topics(auth: dict = Depends(verify_auth)):
    """Return all categories with their topics and questions."""
    store = get_hciot_topic_store()
    categories = store.list_categories()
    return {"categories": categories}
