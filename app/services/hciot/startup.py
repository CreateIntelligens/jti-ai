"""
HCIoT-specific startup / initialization logic.

Called from deps.init_managers() during application startup.
"""

import logging

from app.services.hciot.image_backup import backup_hciot_images
from app.services.hciot.knowledge_backup import backup_hciot_knowledge_files

logger = logging.getLogger(__name__)


def hciot_startup() -> None:
    """Run all HCIoT-specific initialization tasks."""
    # Topic data is now managed via the admin API / CSV upload.
    # No seed step needed.
    try:
        backup_hciot_images()
    except Exception as exc:
        logger.warning("[HCIoT Images] Local backup skipped: %s", exc)
    try:
        backup_hciot_knowledge_files()
    except Exception as exc:
        logger.warning("[HCIoT Knowledge] Local backup skipped: %s", exc)
