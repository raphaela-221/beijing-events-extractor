"""后端 CLI：管理账号。

用法：
  python -m backend.cli set-password <username> [<password>]
  python -m backend.cli list-users
"""
from __future__ import annotations

import getpass
import sys

import bcrypt

from backend.app import auth, config


def cmd_set_password(username: str, password: str | None) -> int:
    auth.seed_users_if_empty()
    users = auth.load_users()
    if username not in users:
        print(f"用户 {username} 不存在，已新建（role=operator）")
        users[username] = {"role": "operator", "display_name": username}
    pw = password or getpass.getpass(f"为 {username} 设置密码: ")
    users[username]["password_hash"] = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    auth.save_users(users)
    print(f"已设置 {username} 的密码（写入 {config.USERS_PATH}）")
    return 0


def cmd_list_users() -> int:
    auth.seed_users_if_empty()
    users = auth.load_users()
    for name, u in users.items():
        print(f"{name}\t{u.get('role')}\t{u.get('display_name', name)}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "set-password":
        if len(sys.argv) < 3:
            print("用法: set-password <username> [<password>]")
            return 1
        return cmd_set_password(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    if cmd == "list-users":
        return cmd_list_users()
    print(f"未知命令: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
