"""
Seed HCIoT topic categories from JSON into MongoDB.

Called during startup. Only seeds if the collection is empty — preserving
any edits made via the admin API after first deploy.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

HCIOT_TOPICS_PATH = Path("data/hciot_topics.json")


def migrate_hciot_topics() -> None:
    """Seed hciot_topics collection from JSON if empty."""
    from app.services.hciot.topic_store import get_hciot_topic_store

    store = get_hciot_topic_store()
    existing = store.list_categories()
    if existing:
        logger.info("[Startup] HCIoT topics already exist (%d categories), skipping seed", len(existing))
        return

    if not HCIOT_TOPICS_PATH.exists():
        logger.warning("[Startup] HCIoT topics JSON not found: %s", HCIOT_TOPICS_PATH)
        return

    seed_data = json.loads(HCIOT_TOPICS_PATH.read_text(encoding="utf-8"))
    for category in seed_data:
        store.upsert_category(category["id"], category)

    print(f"[Startup] ✅ Seeded HCIoT topics: {len(seed_data)} categories")
