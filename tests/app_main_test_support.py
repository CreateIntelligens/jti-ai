import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])


def _ensure_project_root_on_path() -> None:
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)


def _build_tts_jobs_module() -> MagicMock:
    module = MagicMock()
    module.TtsJobManager = MagicMock()
    module.jti_tts_job_manager = MagicMock()
    module.hciot_tts_job_manager = MagicMock()
    return module


def install_app_import_mocks() -> None:
    _ensure_project_root_on_path()

    mock_db = MagicMock()
    mock_mongo_client_module = MagicMock()
    mock_mongo_client_module.get_mongo_db.return_value = mock_db
    sys.modules.setdefault("app.services.mongo_client", mock_mongo_client_module)

    sys.modules.setdefault("app.services.tts_jobs", _build_tts_jobs_module())


def get_test_app():
    install_app_import_mocks()
    from app.main import app

    return app
