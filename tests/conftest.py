import pytest


def pytest_configure(config):
    # Dynamically ignore starlette test client deprecation warning inside pytest
    config.addinivalue_line(
        "filterwarnings",
        "ignore:.*Using .httpx. with .starlette.testclient. is deprecated.*"
    )


@pytest.fixture(autouse=True)
def _reset_topics_read_state(monkeypatch):
    """測試一律直查 store，並隔離每個案例的 process-level seed 狀態。

    測試用 FakeStore，但快取會寫進真實 Redis：跨測試殘留會讓後一個測試讀到
    前一個的資料。這些狀態都是效能層，重設不改變回傳語意。
    """
    from app.routers._shared import plain_topics_admin
    from app.services._shared import topics_cache

    monkeypatch.setattr(topics_cache, "_get_client", lambda: None)
    plain_topics_admin.reset_seed_guard()
