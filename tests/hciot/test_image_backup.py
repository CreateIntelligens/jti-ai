from app.services.hciot.image_backup import backup_hciot_images


class FakeStore:
    def __init__(self):
        self.images = [
            {"image_id": "A0", "content_type": "image/png"},
            {"image_id": "PRP (1)", "content_type": "image/jpeg"},
            {"image_id": "missing", "content_type": "image/jpeg"},
        ]
        self.payloads = {
            "A0": {"data": b"png-data", "content_type": "image/png"},
            "PRP (1)": {"data": b"jpg-data", "content_type": "image/jpeg"},
            "missing": None,
        }

    def list_images(self):
        return list(self.images)

    def get_image(self, image_id: str):
        return self.payloads[image_id]


def test_backup_hciot_images_writes_db_images_to_local_directory(tmp_path):
    result = backup_hciot_images(store=FakeStore(), output_dir=tmp_path)

    assert result == {"total": 3, "written": 2, "skipped": 1, "failed": 0}
    assert (tmp_path / "A0.png").read_bytes() == b"png-data"
    assert (tmp_path / "PRP (1).jpg").read_bytes() == b"jpg-data"
    assert not (tmp_path / "missing.jpg").exists()


def test_backup_hciot_images_skips_unchanged_files(tmp_path):
    store = FakeStore()

    first = backup_hciot_images(store=store, output_dir=tmp_path)
    second = backup_hciot_images(store=store, output_dir=tmp_path)

    assert first == {"total": 3, "written": 2, "skipped": 1, "failed": 0}
    assert second == {"total": 3, "written": 0, "skipped": 3, "failed": 0}
