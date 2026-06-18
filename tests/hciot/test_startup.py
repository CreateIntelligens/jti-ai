from unittest.mock import patch

from app.services.hciot.startup import hciot_startup


def test_hciot_startup_backs_up_images():
    with (
        patch("app.services.hciot.startup.backup_hciot_images") as image_backup,
        patch("app.services.hciot.startup.backup_hciot_knowledge_files") as knowledge_backup,
    ):
        hciot_startup()

    image_backup.assert_called_once_with()
    knowledge_backup.assert_called_once_with()


def test_hciot_startup_continues_when_image_backup_fails():
    with (
        patch("app.services.hciot.startup.backup_hciot_images", side_effect=RuntimeError("db unavailable")),
        patch("app.services.hciot.startup.backup_hciot_knowledge_files") as knowledge_backup,
    ):
        hciot_startup()

    knowledge_backup.assert_called_once_with()


def test_hciot_startup_continues_when_knowledge_backup_fails():
    with (
        patch("app.services.hciot.startup.backup_hciot_images") as image_backup,
        patch("app.services.hciot.startup.backup_hciot_knowledge_files", side_effect=RuntimeError("db unavailable")),
    ):
        hciot_startup()

    image_backup.assert_called_once_with()
