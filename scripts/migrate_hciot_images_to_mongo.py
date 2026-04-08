import os
import mimetypes
from pathlib import Path

# Ensure we can import app
import sys
sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from app.services.hciot.image_store import get_hciot_image_store

# Default directory in Docker is /app/data/hciot/images
# Local directory might be data/hciot/images
DEFAULT_IMAGES_DIR = os.getenv("HCIOT_IMAGES_DIR", "/app/data/hciot/images")
if not os.path.exists(DEFAULT_IMAGES_DIR):
    # Fallback to local data dir if /app doesn't exist
    DEFAULT_IMAGES_DIR = "data/hciot/images"

def migrate_images(images_dir: str = DEFAULT_IMAGES_DIR):
    path = Path(images_dir)
    if not path.exists():
        print(f"Error: Directory {images_dir} does not exist.")
        return

    store = get_hciot_image_store()
    
    files = [f for f in path.iterdir() if f.is_file()]
    print(f"Found {len(files)} files in {images_dir}")

    migrated = 0
    skipped = 0
    failed = 0

    for file_path in files:
        # Skip hidden files
        if file_path.name.startswith("."):
            continue
            
        image_id = file_path.stem
        
        if store.image_exists(image_id):
            print(f"Skipping {image_id} (already in MongoDB)")
            skipped += 1
            continue
            
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            
            mime = mimetypes.guess_type(str(file_path))[0] or "image/jpeg"
            
            success = store.insert_image(image_id, data, content_type=mime)
            if success:
                print(f"Migrated {image_id} ({mime})")
                migrated += 1
            else:
                print(f"Failed to migrate {image_id}")
                failed += 1
        except Exception as e:
            print(f"Error migrating {file_path.name}: {e}")
            failed += 1

    print("\nMigration Summary:")
    print(f"Total files: {len(files)}")
    print(f"Successfully migrated: {migrated}")
    print(f"Skipped (existing): {skipped}")
    print(f"Failed: {failed}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Migrate HCIoT images to MongoDB")
    parser.add_argument("--dir", help="Directory containing images", default=DEFAULT_IMAGES_DIR)
    args = parser.parse_args()
    
    migrate_images(args.dir)
