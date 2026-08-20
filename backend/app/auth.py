"""登录 / 角色 / session。账号存 config/users.json（gitignored，bcrypt 哈希）。
红线：绝不写 .env。session secret 走 config/session_secret（见 config.py）。"""
from __future__ import annotations

import json
from typing import Optional

import bcrypt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import config  # auth 与 config 同在 backend/app/，单点

router = APIRouter(prefix="/api/auth", tags=["auth"])

_DEFAULT_PASSWORD = "change-me"


class LoginIn(BaseModel):
    username: str
    password: str


def load_users() -> dict:
    if not config.USERS_PATH.exists():
        return {}
    return json.loads(config.USERS_PATH.read_text(encoding="utf-8"))


def save_users(users: dict) -> None:
    config.ensure_dirs()
    config.USERS_PATH.write_text(
        json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def seed_users_if_empty() -> None:
    if config.USERS_PATH.exists():
        return
    users = {
        "admin": {
            "password_hash": bcrypt.hashpw(_DEFAULT_PASSWORD.encode(), bcrypt.gensalt()).decode(),
            "role": "admin",
            "display_name": "管理员",
        },
        "operator": {
            "password_hash": bcrypt.hashpw(_DEFAULT_PASSWORD.encode(), bcrypt.gensalt()).decode(),
            "role": "operator",
            "display_name": "操作员",
        },
    }
    save_users(users)


def current_user(request: Request) -> dict | None:
    return request.session.get("user")


def require_user(request: Request) -> dict:
    u = current_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="未登录")
    return u


def require_admin(request: Request) -> dict:
    u = require_user(request)
    if u.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return u


@router.post("/login")
def login(body: LoginIn, request: Request) -> dict:
    seed_users_if_empty()
    users = load_users()
    u = users.get(body.username)
    if not u or not bcrypt.checkpw(
        body.password.encode(), u["password_hash"].encode()
    ):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    sess = {
        "username": body.username,
        "role": u["role"],
        "display_name": u.get("display_name", body.username),
    }
    request.session["user"] = sess
    return sess


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict:
    u = current_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="未登录")
    return u


# ---- 修改密码（用户自助，需旧密码）----
class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
def change_password(body: ChangePasswordIn, request: Request) -> dict:
    u = require_user(request)
    users = load_users()
    rec = users.get(u["username"])
    if not rec or not bcrypt.checkpw(
        body.old_password.encode(), rec["password_hash"].encode()
    ):
        raise HTTPException(status_code=401, detail="旧密码错误")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    rec["password_hash"] = bcrypt.hashpw(
        body.new_password.encode(), bcrypt.gensalt()
    ).decode()
    save_users(users)
    return {"ok": True}


# ---- 账号管理（admin）----
class CreateUserIn(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    role: str = "operator"


class UpdateUserIn(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None
    display_name: Optional[str] = None


@router.get("/users")
def list_users_api(request: Request) -> dict:
    require_admin(request)
    users = load_users()
    items = [
        {
            "username": name,
            "role": v.get("role", "operator"),
            "display_name": v.get("display_name", name),
        }
        for name, v in users.items()
    ]
    return {"items": items}


@router.post("/users")
def create_user(body: CreateUserIn, request: Request) -> dict:
    require_admin(request)
    if body.role not in ("admin", "operator"):
        raise HTTPException(status_code=400, detail="role 必须是 admin 或 operator")
    users = load_users()
    if body.username in users:
        raise HTTPException(status_code=409, detail="用户名已存在")
    users[body.username] = {
        "password_hash": bcrypt.hashpw(
            body.password.encode(), bcrypt.gensalt()
        ).decode(),
        "role": body.role,
        "display_name": body.display_name or body.username,
    }
    save_users(users)
    return {"ok": True}


@router.patch("/users/{username}")
def update_user(username: str, body: UpdateUserIn, request: Request) -> dict:
    require_admin(request)
    users = load_users()
    if username not in users:
        raise HTTPException(status_code=404, detail="用户不存在")
    rec = users[username]
    if body.role is not None:
        if body.role not in ("admin", "operator"):
            raise HTTPException(status_code=400, detail="role 必须是 admin 或 operator")
        rec["role"] = body.role
    if body.password is not None:
        if len(body.password) < 6:
            raise HTTPException(status_code=400, detail="密码至少 6 位")
        rec["password_hash"] = bcrypt.hashpw(
            body.password.encode(), bcrypt.gensalt()
        ).decode()
    if body.display_name is not None:
        rec["display_name"] = body.display_name
    save_users(users)
    return {"ok": True}
