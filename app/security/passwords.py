"""密碼雜湊工具 (bcrypt)。

- hash_password: 產生可存放於資料庫的 utf-8 字串雜湊。
- verify_password: 常數時間比對;雜湊壞掉時回傳 False 而非丟例外。

注意 bcrypt 僅取密碼前 72 bytes,超長密碼交由 bcrypt 自行截斷,不額外處理。
"""

import logging

logger = logging.getLogger(__name__)

# bcrypt 只看密碼前 72 bytes。明確截斷(而非交由 bcrypt 隱式處理),
# hash/verify 共用此規則,避免兩處 slice 漂移導致雜湊永遠對不上。
_BCRYPT_MAX_BYTES = 72


def _to_bcrypt_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    """對明文密碼產生 bcrypt 雜湊,回傳可存放的 utf-8 字串。"""
    import bcrypt

    hashed = bcrypt.hashpw(_to_bcrypt_bytes(plain), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """以常數時間比對明文與雜湊。

    雜湊格式錯誤或 bcrypt 無法使用時回傳 False,絕不丟例外。
    """
    if not plain or not hashed:
        return False
    try:
        import bcrypt

        return bcrypt.checkpw(_to_bcrypt_bytes(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError, ImportError) as exc:
        logger.debug("[verify_password] 比對失敗: %s", exc)
        return False
