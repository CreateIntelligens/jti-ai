"""
HCIoT-specific startup / initialization logic.

Called from deps.init_managers() during application startup.
"""

import logging

logger = logging.getLogger(__name__)


def hciot_startup() -> None:
    """Run all HCIoT-specific initialization tasks."""
    # Topic data is now managed via the admin API / CSV upload.
    # No seed step needed.
    pass
