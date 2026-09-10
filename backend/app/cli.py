"""管理命令行入口：python -m app.cli <command>"""

import argparse
import getpass
import sys

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.admin import Admin


def reset_admin_password(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        admin = db.query(Admin).filter(Admin.username == args.username).first()
        if admin is None:
            print(f"管理员 '{args.username}' 不存在", file=sys.stderr)
            raise SystemExit(1)
        password = args.password or getpass.getpass("新密码：")
        admin.password_hash = hash_password(password)
        db.commit()
        print(f"管理员 '{args.username}' 密码已重置")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset_parser = subparsers.add_parser("reset-admin-password", help="重置管理员密码")
    reset_parser.add_argument("--username", default="admin")
    reset_parser.add_argument("--password", default=None, help="不传则交互式输入")
    reset_parser.set_defaults(func=reset_admin_password)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
