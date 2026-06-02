"""密碼雜湊工具測試 (app.security.passwords)。

純邏輯測試。需要 bcrypt 的雜湊測試在無 bcrypt 環境下會 skip;
verify_password 對壞掉雜湊回傳 False (不丟例外) 的行為一律驗證,不需 bcrypt。
"""

import importlib.util

import pytest

from app.security.passwords import hash_password, verify_password

HAS_BCRYPT = importlib.util.find_spec("bcrypt") is not None
requires_bcrypt = pytest.mark.skipif(not HAS_BCRYPT, reason="bcrypt 未安裝")


@requires_bcrypt
def test_hash_is_not_reversible():
    plain = "s3cret-pw"
    hashed = hash_password(plain)
    assert hashed != plain
    assert isinstance(hashed, str)


@requires_bcrypt
def test_same_plain_hashes_differently_due_to_salt():
    plain = "same-password"
    assert hash_password(plain) != hash_password(plain)


@requires_bcrypt
def test_verify_true_for_correct_password():
    plain = "correct horse battery staple"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


@requires_bcrypt
def test_verify_false_for_wrong_password():
    hashed = hash_password("right-password")
    assert verify_password("wrong-password", hashed) is False


@requires_bcrypt
def test_long_password_does_not_crash():
    plain = "x" * 200
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


@pytest.mark.parametrize(
    "garbage",
    ["", "not-a-bcrypt-hash", "$2b$invalid", "12345"],
)
def test_verify_false_for_garbage_hash(garbage):
    """壞掉的雜湊一律回傳 False,不丟例外 (即使 bcrypt 未安裝)。"""
    assert verify_password("anything", garbage) is False
