"""建立使用者帳號 (含第一個 super_admin)。

在 backend 環境內執行:
    python scripts/create_user.py --username spark --role super_admin
    python scripts/create_user.py --username cust_a --role user --app hciot

密碼以互動方式輸入 (getpass),不寫在命令列,避免落入 shell 歷史 / log。
密碼由 UserManager 以 bcrypt 雜湊存放,不存明文。
"""

import argparse
import getpass
import sys
from pathlib import Path

# 讓腳本不論從何處執行都能 import app 套件 (專案根 = scripts/ 的上一層)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.users import ALLOWED_ROLES, UserManager


def _prompt_password() -> str:
    """互動輸入密碼並二次確認;不符或為空則退出。"""
    pw1 = getpass.getpass("密碼: ")
    if not pw1:
        raise SystemExit("ERROR: 密碼不可為空")
    pw2 = getpass.getpass("再次輸入密碼: ")
    if pw1 != pw2:
        raise SystemExit("ERROR: 兩次密碼不一致")
    return pw1


def main() -> None:
    parser = argparse.ArgumentParser(description="建立使用者帳號")
    parser.add_argument("--username", required=True, help="登入帳號 (唯一)")
    parser.add_argument(
        "--role",
        required=True,
        choices=sorted(ALLOWED_ROLES),
        help="角色: super_admin / admin / user",
    )
    parser.add_argument(
        "--scope",
        default=None,
        help="所屬 scope (e.g. hciot/jti/general/key_name:<name>);role=user 必填,其餘留空",
    )
    parser.add_argument(
        "--store-name",
        default=None,
        help="綁定的知識庫 (選填)",
    )
    args = parser.parse_args()

    manager = UserManager()

    if manager.get_by_username(args.username):
        raise SystemExit(f"ERROR: 帳號已存在: {args.username}")

    password = _prompt_password()

    try:
        user = manager.create_user(
            username=args.username,
            password=password,
            role=args.role,
            scope=args.scope,
            store_name=args.store_name,
            created_by="seed-script",
        )
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    print(
        f"已建立: id={user.id} username={user.username} "
        f"role={user.role} scope={user.scope}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
