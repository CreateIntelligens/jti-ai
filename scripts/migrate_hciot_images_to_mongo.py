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

DEFAULT_IMAGES_DIR = os.getenv("HCIOT_IMAGES_DIR") or str(PROJECT_ROOT / "data" / "hciot" / "images")


def migrate_images(images_dir: str = DEFAULT_IMAGES_DIR):
    path = Path(images_dir)
    if not path.exists():
        print(f"Error: Directory {images_dir} does not exist.")
        return

    store = get_hciot_image_store()
    files = [f for f in path.iterdir() if f.is_file() and not f.name.startswith(".")]
    print(f"Found {len(files)} files in {images_dir}")

    migrated = 0
    replaced = 0
    failed = 0
    for file_path in files:
        image_id = file_path.stem
        try:
            data = file_path.read_bytes()
            mime = mimetypes.guess_type(str(file_path))[0] or "image/jpeg"
            result = store.upsert_image(image_id, data, content_type=mime)
            if result["success"]:
                if result["replaced"]:
                    print(f"Replaced {image_id} ({mime})")
                    replaced += 1
                else:
                    print(f"Migrated {image_id} ({mime})")
                    migrated += 1
            else:
                print(f"Failed to upsert {image_id}")
                failed += 1
        except Exception as e:
            print(f"Error migrating {file_path.name}: {e}")
            failed += 1

    print("\nMigration Summary:")
    print(f"Total files: {len(files)}")
    print(f"Inserted: {migrated}")
    print(f"Replaced: {replaced}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Migrate HCIoT images to MongoDB")
    parser.add_argument("--dir", help="Directory containing images", default=DEFAULT_IMAGES_DIR)
    args = parser.parse_args()
    migrate_images(args.dir)
