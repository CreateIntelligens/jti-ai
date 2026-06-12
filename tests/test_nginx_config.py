from pathlib import Path


def test_api_proxy_preserves_public_host_for_same_origin_auth():
    config = Path("docker/frontend/nginx.conf.template").read_text()

    assert "proxy_set_header Host $host;" in config
    assert "proxy_set_header X-Forwarded-Host $host;" in config
