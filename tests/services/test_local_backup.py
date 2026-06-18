import json

from app.services._shared.local_backup import (
    safe_backup_filename,
    write_bytes_if_changed,
    write_json_manifest,
)


def test_write_bytes_if_changed_reports_written_then_skipped(tmp_path):
    target = tmp_path / "backup.bin"

    assert write_bytes_if_changed(target, b"payload") == "written"
    assert target.read_bytes() == b"payload"
    assert write_bytes_if_changed(target, b"payload") == "skipped"
    assert write_bytes_if_changed(target, b"new") == "written"
    assert target.read_bytes() == b"new"


def test_write_json_manifest_serializes_stable_utf8_json(tmp_path):
    target = tmp_path / "manifest.json"

    write_json_manifest(target, {"files": [{"filename": "骨科.csv"}]})

    assert json.loads(target.read_text()) == {"files": [{"filename": "骨科.csv"}]}
    assert target.read_text().endswith("\n")


def test_safe_backup_filename_drops_path_components_and_unsafe_separators():
    assert safe_backup_filename("../folder/name.csv") == "name.csv"
    assert safe_backup_filename("folder\\name.csv") == "folder_name.csv"
