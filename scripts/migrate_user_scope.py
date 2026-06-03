#!/usr/bin/env python3
"""Migration: rename users.app -> users.scope (值不變,冪等)。

在 backend 環境內執行:
    python scripts/migrate_user_scope.py
唯讀預覽:
    python scripts/migrate_user_scope.py --dry-run
"""

import argparse
import logging
import sys
from pathlib import Path

# Load env variables from .env
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.users import UserManager  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate_user_scope")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rename users.app to users.scope.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    collection = UserManager().collection
    cursor = collection.find({"app": {"$exists": True}})
    count = 0
    for doc in cursor:
        app_value = doc.get("app")
        logger.info(
            "user %s: app=%r -> scope (dry_run=%s)",
            doc.get("username"),
            app_value,
            args.dry_run,
        )
        if not args.dry_run:
            collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"scope": app_value}, "$unset": {"app": ""}},
            )
        count += 1
    logger.info("done. %d users %s.", count, "previewed" if args.dry_run else "migrated")


if __name__ == "__main__":
    main()
