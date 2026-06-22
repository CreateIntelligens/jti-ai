def pytest_configure(config):
    # Dynamically ignore starlette test client deprecation warning inside pytest
    config.addinivalue_line(
        "filterwarnings",
        "ignore:.*Using .httpx. with .starlette.testclient. is deprecated.*"
    )
