"""生成 bcrypt 密码哈希，用于 .env 的 AUTH_PASSWORD_HASH。

用法（在 backend 目录）：
    uv run python scripts/gen_password_hash.py
    # 然后输入密码（不回显），输出 hash 复制到 .env
"""
from __future__ import annotations

import getpass
import sys

sys.path.insert(0, ".")

from app.middleware.basic_auth import hash_password  # noqa: E402


def main() -> None:
    pwd = getpass.getpass("password: ")
    pwd2 = getpass.getpass("confirm : ")
    if pwd != pwd2:
        print("✗ 两次输入不一致")
        sys.exit(1)
    if len(pwd) < 8:
        print("⚠️  建议密码至少 8 位")

    h = hash_password(pwd)
    print()
    print("AUTH_PASSWORD_HASH=" + h)


if __name__ == "__main__":
    main()
