from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "docker" / "backend" / "Dockerfile"


def _stage(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_backend_builder_installs_via_uv_sync_from_lock():
    """backend 依賴由 uv sync --frozen 從 uv.lock 安裝（單一事實來源）。

    舊架構用 pip wheelhouse + /wheels glob，曾因 glob 把同套件多版本都當顯式
    安裝目標而解析錯誤；改 uv 後該風險消失，且不再有任何 requirements 檔。
    """
    text = DOCKERFILE.read_text()
    builder_stage = _stage(
        text,
        "# ---------- builder ----------",
        "# ---------- runner ----------",
    )

    # 由 lock frozen 安裝，不重解析、版本完全照 uv.lock
    assert "uv sync --frozen" in builder_stage
    # backend 範圍：主 deps + backend-heavy，不裝 dev/torch
    assert "--no-default-groups --group backend-heavy" in builder_stage
    # 不再走 pip wheelhouse / requirements 檔
    assert "/wheels" not in text
    assert "requirements.txt" not in text


def test_backend_runner_copies_venv_and_puts_it_on_path():
    text = DOCKERFILE.read_text()
    runner_stage = _stage(text, "# ---------- runner ----------", "ENTRYPOINT")

    assert "COPY --from=builder /app/.venv /app/.venv" in runner_stage
    assert "/app/.venv/bin" in runner_stage
