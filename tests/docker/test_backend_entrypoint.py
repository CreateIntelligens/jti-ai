import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "docker" / "backend" / "entrypoint.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _run_entrypoint(tmp_path: Path, env: dict[str, str] | None = None, args: list[str] | None = None):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "uvicorn", "#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
    _write_executable(fake_bin / "custom-cmd", "#!/bin/sh\nprintf 'custom:%s\\n' \"$@\"\n")

    run_env = os.environ.copy()
    run_env.pop("MODE", None)
    run_env.pop("PORT", None)
    run_env.pop("BACKEND_PORT", None)
    run_env["PATH"] = f"{fake_bin}:{run_env['PATH']}"
    if env:
        run_env.update(env)

    return subprocess.run(
        ["sh", str(ENTRYPOINT), *(args or [])],
        cwd=ROOT,
        env=run_env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_dev_mode_uses_reload(tmp_path: Path):
    result = _run_entrypoint(tmp_path, {"MODE": "dev", "BACKEND_PORT": "8914"})

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8914",
        "--reload",
    ]


def test_prod_mode_uses_two_workers(tmp_path: Path):
    result = _run_entrypoint(tmp_path, {"MODE": "prod", "PORT": "8008"})

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8008",
        "--workers",
        "2",
    ]


def test_unset_mode_defaults_to_prod(tmp_path: Path):
    result = _run_entrypoint(tmp_path)

    assert result.returncode == 0
    assert result.stdout.splitlines()[-2:] == ["--workers", "2"]


def test_invalid_mode_fails_fast(tmp_path: Path):
    result = _run_entrypoint(tmp_path, {"MODE": "staging"})

    assert result.returncode == 2
    assert "MODE must be 'dev' or 'prod'" in result.stderr


def test_explicit_command_is_respected(tmp_path: Path):
    result = _run_entrypoint(tmp_path, {"MODE": "staging"}, ["custom-cmd", "hello"])

    assert result.returncode == 0
    assert result.stdout == "custom:hello\n"
