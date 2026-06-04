import pytest
from fastapi import HTTPException

from app.auth import can_access_kb, require_kb_access


@pytest.mark.parametrize(
    ("auth", "app", "expected"),
    [
        ({"role": "super_admin", "scope": None}, "hciot", True),
        ({"role": "admin", "scope": "jti"}, "hciot", True),
        ({"role": "user", "scope": "hciot"}, "hciot", True),
        ({"role": "user", "scope": "hciot"}, "jti", False),
        ({"role": "guest"}, "hciot", False),
    ],
)
def test_can_access_kb(auth: dict, app: str, expected: bool):
    assert can_access_kb(auth, app) is expected


def test_require_kb_access_returns_auth_for_matching_scope():
    auth = {"role": "user", "scope": "hciot", "user_id": "u1"}

    assert require_kb_access("hciot")(auth) is auth


def test_require_kb_access_rejects_cross_scope_user():
    with pytest.raises(HTTPException) as exc:
        require_kb_access("jti")({"role": "user", "scope": "hciot"})

    assert exc.value.status_code == 403
