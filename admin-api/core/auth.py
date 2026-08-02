"""Login, session validation, lockout. Sessions store only the token's
SHA-256 hash; a storage leak never yields usable sessions."""
from datetime import UTC, datetime, timedelta

from . import security, tables
from .http import ApiError

SESSION_PK = "session"
USER_PK = "user"
SESSION_DAYS = 7
SLIDING_REFRESH_SECONDS = 3600
MAX_FAILED = 5
LOCKOUT_MINUTES = 15


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def public_user(row: dict) -> dict:
    return {
        "username": row.get("RowKey", ""),
        "display_name": row.get("display_name", ""),
        "role": row.get("role", "admin"),
        "is_active": bool(row.get("is_active", True)),
        "last_login_at": row.get("last_login_at", ""),
    }


def login(username: str, password: str) -> dict:
    username = (username or "").strip().lower()
    if not username or not password:
        raise ApiError(400, "username and password are required")
    row = tables.get_entity(tables.TABLE_USERS, USER_PK, username)
    if row is None or not bool(row.get("is_active", True)):
        # burn comparable time so unknown users aren't distinguishable
        security.verify_password(password, security.hash_password("x"))
        raise ApiError(401, "invalid credentials")

    locked_until = row.get("locked_until", "")
    if locked_until and locked_until > _iso(_now()):
        raise ApiError(423, "account locked — try again later")

    if not security.verify_password(password, row.get("password_hash", "")):
        failed = int(row.get("failed_attempts", 0)) + 1
        update = {"PartitionKey": USER_PK, "RowKey": username, "failed_attempts": failed}
        if failed >= MAX_FAILED:
            update["locked_until"] = _iso(_now() + timedelta(minutes=LOCKOUT_MINUTES))
            update["failed_attempts"] = 0
        tables.upsert(tables.TABLE_USERS, update)
        raise ApiError(401, "invalid credentials")

    tables.upsert(tables.TABLE_USERS, {
        "PartitionKey": USER_PK, "RowKey": username,
        "failed_attempts": 0, "locked_until": "",
        "last_login_at": _iso(_now()),
    })
    token = security.new_token()
    tables.upsert(tables.TABLE_SESSIONS, {
        "PartitionKey": SESSION_PK,
        "RowKey": security.token_hash(token),
        "username": username,
        "created_at": _iso(_now()),
        "last_seen_at": _iso(_now()),
        "expires_at": _iso(_now() + timedelta(days=SESSION_DAYS)),
    })
    return {"token": token, "user": public_user({**row, "RowKey": username})}


def validate_token(token: str) -> dict:
    if not token:
        raise ApiError(401, "missing bearer token")
    rk = security.token_hash(token)
    session = tables.get_entity(tables.TABLE_SESSIONS, SESSION_PK, rk)
    if session is None:
        raise ApiError(401, "invalid session")
    if session.get("expires_at", "") <= _iso(_now()):
        tables.delete(tables.TABLE_SESSIONS, SESSION_PK, rk)
        raise ApiError(401, "session expired")
    user = tables.get_entity(tables.TABLE_USERS, USER_PK, session.get("username", ""))
    if user is None or not bool(user.get("is_active", True)):
        raise ApiError(401, "user disabled")
    last_seen = session.get("last_seen_at", "")
    if not last_seen or last_seen < _iso(_now() - timedelta(seconds=SLIDING_REFRESH_SECONDS)):
        tables.upsert(tables.TABLE_SESSIONS, {
            "PartitionKey": SESSION_PK, "RowKey": rk,
            "last_seen_at": _iso(_now()),
            "expires_at": _iso(_now() + timedelta(days=SESSION_DAYS)),
        })
    return user


def logout(token: str) -> None:
    if token:
        tables.delete(tables.TABLE_SESSIONS, SESSION_PK, security.token_hash(token))
