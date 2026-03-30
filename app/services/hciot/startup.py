"""
HCIoT-specific startup / initialization logic.

Called from deps.init_managers() during application startup.
"""

import logging

logger = logging.getLogger(__name__)


def hciot_startup() -> None:
    """Run all HCIoT-specific initialization tasks."""
    _seed_topic_data()


def _seed_topic_data() -> None:
    """Seed HCIoT topic categories from JSON into MongoDB."""
    from .migrate_topics import migrate_hciot_topics
    migrate_hciot_topics()
