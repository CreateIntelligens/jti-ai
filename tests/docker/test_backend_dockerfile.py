from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "docker" / "backend" / "Dockerfile"


def _stage(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_backend_deps_stage_installs_from_requirements_not_wheel_glob():
    text = DOCKERFILE.read_text()
    deps_stage = _stage(
        text,
        "# ---------- Stage 2: deps ----------",
        "# ---------- Stage 3: runner ----------",
    )

    assert "/wheels/*.whl" not in deps_stage
    assert "-r /tmp/backend-heavy-requirements.txt" in deps_stage
    assert "-r /tmp/requirements.txt" in deps_stage
