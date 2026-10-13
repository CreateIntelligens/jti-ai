"""在主機上重設帳號密碼（不提供 API，避免被冒用的管理員身分拿去改別人的密碼）。

用法（在 backend 容器內）:
    python scripts/reset_password.py --username admin

新密碼以互動方式輸入（getpass），不寫在命令列，避免落入 shell 歷史 / log。
重設密碼不會讓既有的登入 token 失效；要強制所有人重新登入，請一併更換 SESSION_JWT_SECRET。
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.users import UserManager


def main() -> None:
    parser = argparse.ArgumentParser(description="重設帳號密碼")
    parser.add_argument("--username", required=True, help="要重設的登入帳號")
    args = parser.parse_args()

    manager = UserManager()
    if not manager.get_by_username(args.username):
        raise SystemExit(f"ERROR: 找不到帳號: {args.username}")

    pw1 = getpass.getpass("新密碼: ")
    pw2 = getpass.getpass("再次輸入新密碼: ")
    if pw1 != pw2:
        raise SystemExit("ERROR: 兩次密碼不一致")

    try:
        manager.set_password(args.username, pw1)
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print(f"已重設 {args.username} 的密碼")


if __name__ == "__main__":
    main()
