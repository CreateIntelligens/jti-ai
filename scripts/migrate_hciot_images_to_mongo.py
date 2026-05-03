import logging
import mimetypes
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from app.services.hciot.image_store import get_hciot_image_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_IMAGES_DIR = os.getenv("HCIOT_IMAGES_DIR") or str(PROJECT_ROOT / "data" / "hciot" / "images")


def migrate_images(images_dir: str = DEFAULT_IMAGES_DIR, force: bool = False):
    path = Path(images_dir)
    if not path.exists():
        logger.error("Directory %s does not exist.", images_dir)
        return

    store = get_hciot_image_store()
    files = [f for f in path.iterdir() if f.is_file() and not f.name.startswith(".")]
    logger.info("Found %d files in %s", len(files), images_dir)

    migrated = 0
    replaced = 0
    skipped = 0
    failed = 0
    for file_path in files:
        image_id = file_path.stem
        try:
            if not force and store.image_exists(image_id):
                logger.info("Skipping %s (already in MongoDB; use --force to overwrite)", image_id)
                skipped += 1
                continue
            data = file_path.read_bytes()
            mime = mimetypes.guess_type(str(file_path))[0] or "image/jpeg"
            result = store.upsert_image(image_id, data, content_type=mime)
            if result["success"]:
                if result["replaced"]:
                    logger.info("Replaced %s (%s)", image_id, mime)
                    replaced += 1
                else:
                    logger.info("Migrated %s (%s)", image_id, mime)
                    migrated += 1
            else:
                logger.warning("Failed to upsert %s", image_id)
                failed += 1
        except Exception as e:
            logger.error("Error migrating %s: %s", file_path.name, e)
            failed += 1

    logger.info(
        "Migration summary: total=%d inserted=%d replaced=%d skipped=%d failed=%d",
        len(files), migrated, replaced, skipped, failed,
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Migrate HCIoT images to MongoDB")
    parser.add_argument("--dir", help="Directory containing images", default=DEFAULT_IMAGES_DIR)
    parser.add_argument("--force", action="store_true", help="Overwrite existing images")
    args = parser.parse_args()
    migrate_images(args.dir, force=args.force)
