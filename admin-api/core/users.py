"""Users CRUD. Creation/password-reset are CLI-driven (Make targets);
the HTTP surface only lists, patches, and soft-deletes."""
from datetime import datetime, timezone

from . import auth, security, tables
from .http import ApiError

_PATCHABLE = {"display_name", "is_active", "role"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_user(username: str, password: str, display_name: str = "", role: str = "admin") -> dict:
    username = username.strip().lower()
    if not username or not password:
        raise ApiError(400, "username and password required")
    if tables.get_entity(tables.TABLE_USERS, auth.USER_PK, username) is not None:
        raise ApiError(409, f"user {username} already exists")
    row = {
        "PartitionKey": auth.USER_PK, "RowKey": username,
        "password_hash": security.hash_password(password),
        "display_name": display_name or username,
        "role": role, "is_active": True,
        "failed_attempts": 0, "locked_until": "",
        "created_at": _now(), "updated_at": _now(), "last_login_at": "",
    }
    tables.upsert(tables.TABLE_USERS, row)
    return auth.public_user(row)


def list_users() -> list[dict]:
    rows = tables.query(tables.TABLE_USERS, f"PartitionKey eq '{auth.USER_PK}'")
    return sorted((auth.public_user(r) for r in rows), key=lambda u: u["username"])


def get_user(username: str) -> dict:
    row = tables.get_entity(tables.TABLE_USERS, auth.USER_PK, username.lower())
    if row is None:
        raise ApiError(404, "user not found")
    return auth.public_user(row)


def patch_user(username: str, changes: dict) -> dict:
    username = username.lower()
    if tables.get_entity(tables.TABLE_USERS, auth.USER_PK, username) is None:
        raise ApiError(404, "user not found")
    update = {k: v for k, v in changes.items() if k in _PATCHABLE}
    if not update:
        raise ApiError(400, f"nothing to update — allowed: {sorted(_PATCHABLE)}")
    update.update({"PartitionKey": auth.USER_PK, "RowKey": username, "updated_at": _now()})
    tables.upsert(tables.TABLE_USERS, update)
    return get_user(username)


def set_password(username: str, password: str) -> None:
    username = username.lower()
    if tables.get_entity(tables.TABLE_USERS, auth.USER_PK, username) is None:
        raise ApiError(404, "user not found")
    tables.upsert(tables.TABLE_USERS, {
        "PartitionKey": auth.USER_PK, "RowKey": username,
        "password_hash": security.hash_password(password),
        "failed_attempts": 0, "locked_until": "", "updated_at": _now(),
    })


def set_active(username: str, active: bool) -> dict:
    return patch_user(username, {"is_active": active})
