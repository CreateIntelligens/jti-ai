#!/usr/bin/env python3
"""Reconcile CLI: 雙向比對與對齊 LanceDB 和 MongoDB vector_backup。

用法:
    python scripts/reconcile_rag.py [--dry-run]
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Iterable

# Load env variables from .env
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.vector_store.lancedb import get_lancedb_store  # noqa: E402
from app.services.vector_store.mongodb_backup import get_mongodb_backup  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reconcile_rag")

KNOWLEDGE_SOURCE_SUFFIX = "_knowledge"


def _canonical_source_type(source_type: str) -> str:
    if source_type.endswith(KNOWLEDGE_SOURCE_SUFFIX):
        return source_type[: -len(KNOWLEDGE_SOURCE_SUFFIX)]
    return source_type


def _knowledge_source_type(source_type: str) -> str:
    if source_type.endswith(KNOWLEDGE_SOURCE_SUFFIX):
        return source_type
    return f"{source_type}{KNOWLEDGE_SOURCE_SUFFIX}"


def _chunks_for_lancedb(cursor: Iterable[dict]) -> list[dict]:
    chunks = []
    for doc in cursor:
        chunk = dict(doc)
        chunk.pop("_id", None)
        chunk.pop("synced_at", None)
        chunks.append(chunk)
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="JTAI RAG LanceDB ↔ MongoDB Vector Reconciler")
    parser.add_argument("--dry-run", action="store_true", help="僅預覽比對結果，不執行對齊")
    args = parser.parse_args()

    lancedb_store = get_lancedb_store()
    mongo_backup = get_mongodb_backup()
    mongo_collection = mongo_backup.collection

    is_authority = os.getenv("RAG_AUTHORITY_DEPLOYMENT", "false").lower() == "true"
    logger.info(f"Authority Deployment status: {is_authority}")

    lancedb_files = set()
    tbl = lancedb_store.table
    if tbl is not None:
        try:
            # 只取所需三欄並用 set 去重，避免在記憶體保留整張表的列（壓測時可達數十萬列）
            rows = tbl.search().select(["source_type", "source_language", "file_id"]).to_list()
            for r in rows:
                source_type = r.get("source_type")
                source_language = r.get("source_language")
                file_id = r.get("file_id")
                if source_type and source_language and file_id:
                    lancedb_files.add((_canonical_source_type(source_type), source_language, file_id))
        except Exception as e:
            logger.error(f"Failed to scan LanceDB: {e}")

    mongo_files = set()
    try:
        pipeline = [
            {
                "$group": {
                    "_id": {
                        "source_type": "$source_type",
                        "source_language": "$source_language",
                        "file_id": "$file_id",
                    }
                }
            }
        ]
        for item in mongo_collection.aggregate(pipeline):
            meta = item["_id"]
            source_type = meta.get("source_type")
            source_language = meta.get("source_language")
            file_id = meta.get("file_id")
            if source_type and source_language and file_id:
                mongo_files.add((_canonical_source_type(source_type), source_language, file_id))
    except Exception as e:
        logger.error(f"Failed to scan MongoDB: {e}")

    logger.info(f"Scan complete. LanceDB has {len(lancedb_files)} files, MongoDB backup has {len(mongo_files)} files.")

    lancedb_only = lancedb_files - mongo_files
    mongo_only = mongo_files - lancedb_files

    logger.info(f"LanceDB only (missing in MongoDB): {len(lancedb_only)}")
    logger.info(f"MongoDB only (missing in LanceDB): {len(mongo_only)}")

    if mongo_only:
        logger.info(">>> Syncing missing files from MongoDB to LanceDB...")
        for source_type, source_language, file_id in mongo_only:
            full_source_type = _knowledge_source_type(source_type)
            logger.info(f"[Mongo -> LanceDB] File: {file_id} ({source_type}/{source_language})")
            if args.dry_run:
                logger.info(f"[Dry Run] Would restore {file_id} to LanceDB")
                continue

            try:
                cursor = mongo_collection.find({
                    "file_id": file_id,
                    "source_type": full_source_type,
                    "source_language": source_language,
                })
                chunks = _chunks_for_lancedb(cursor)
                if chunks:
                    lancedb_store.insert_chunks(chunks)
                    logger.info(f"Restored {len(chunks)} chunks for {file_id}")
            except Exception as e:
                logger.error(f"Failed to restore {file_id} to LanceDB: {e}")

    if lancedb_only:
        if not is_authority:
            logger.warning(
                ">>> Skipping backup of LanceDB-only files because this deployment is NOT the Authority Deployment.\n"
                "Please configure RAG_AUTHORITY_DEPLOYMENT=true on the authority host to back up these files."
            )
            for source_type, source_language, file_id in lancedb_only:
                logger.warning(f"  - Local-only file: {file_id} ({source_type}/{source_language})")
        else:
            logger.info(">>> Syncing missing files from LanceDB to MongoDB...")
            for source_type, source_language, file_id in lancedb_only:
                full_source_type = _knowledge_source_type(source_type)
                logger.info(f"[LanceDB -> Mongo] File: {file_id} ({source_type}/{source_language})")
                if args.dry_run:
                    logger.info(f"[Dry Run] Would backup {file_id} to MongoDB")
                    continue

                try:
                    chunks = lancedb_store.get_file_chunks(file_id, full_source_type, source_language)
                    if chunks:
                        mongo_backup.sync_to_mongodb(chunks)
                        logger.info(f"Backed up {len(chunks)} chunks for {file_id}")
                except Exception as e:
                    logger.error(f"Failed to backup {file_id} to MongoDB: {e}")

    logger.info("Reconciliation process finished.")


if __name__ == "__main__":
    main()
