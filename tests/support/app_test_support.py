import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
_TEST_TTS_CACHE_DIR = "/tmp/jtai-test-tts-cache"
_MODULES_TO_RESET = (
    "app.deps",
    "app.services.jti.tts",
    "app.services.hciot.tts",
    "app.services.jti.main_agent",
    "app.services.hciot.main_agent",
    "app.services.jti.quiz_helpers",
    "app.services.jti.runtime_quiz_flow",
    "app.tools.jti.tool_executor",
    "app.routers.jti.chat",
    "app.routers.hciot.chat",
    "app.routers.general.chat",
    "app.main",
)


def _ensure_project_root_on_path() -> None:
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)


def _build_tts_jobs_module() -> MagicMock:
    module = MagicMock()
    module.TtsJobManager = MagicMock()
    return module


def _reset_modules() -> None:
    for module_name in _MODULES_TO_RESET:
        module = sys.modules.get(module_name)
        if module is not None:
            importlib.reload(module)


def install_app_import_mocks() -> None:
    _ensure_project_root_on_path()
    os.environ.setdefault("TTS_CACHE_DIR", _TEST_TTS_CACHE_DIR)

    mock_db = MagicMock()
    mock_mongo_client_module = MagicMock()
    mock_mongo_client_module.get_mongo_db.return_value = mock_db
    sys.modules["app.services.mongo_client"] = mock_mongo_client_module

    sys.modules["app.services.tts_jobs"] = _build_tts_jobs_module()
    _reset_modules()


def get_test_app():
    install_app_import_mocks()
    from app.main import app

    return app
