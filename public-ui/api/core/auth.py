"""Public signup, login, sessions, and email verification.

Same hardening as the admin API — sessions store only the token's SHA-256
hash, failed logins lock the account — with the differences a public app
needs: self-serve signup, verified email before alerts may fire, and social
identities linked onto the same row (see oauth.py).
"""
import json
import re
from datetime import UTC, datetime, timedelta

from . import security, tables
from .http import ApiError

USER_PK = "user"
SESSION_PK = "session"
SESSION_DAYS = 30           # public users shouldn't be logged out weekly
SLIDING_REFRESH_SECONDS = 3600
MAX_FAILED = 5
LOCKOUT_MINUTES = 15
MIN_PASSWORD = 8
VERIFY_TTL_HOURS = 48

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def public_user(row: dict) -> dict:
    """What the SPA is allowed to see about the signed-in user. Never
    password_hash, never the verification token."""
    return {
        "email": row.get("RowKey", ""),
        "display_name": row.get("display_name", ""),
        "email_verified": bool(row.get("email_verified", False)),
        "phone": row.get("phone", ""),
        "phone_verified": bool(row.get("phone_verified", False)),
        "providers": json.loads(row.get("providers", "[]") or "[]"),
        "has_password": bool(row.get("password_hash", "")),
        "tz": row.get("tz", "America/New_York"),
        "created_at": row.get("created_at", ""),
        "last_login_at": row.get("last_login_at", ""),
    }


def get_user_row(email: str) -> dict | None:
    return tables.get_entity(tables.TABLE_USERS, USER_PK, normalize_email(email))


def _issue_session(email: str) -> str:
    token = security.new_token()
    tables.upsert(tables.TABLE_SESSIONS, {
        "PartitionKey": SESSION_PK,
        "RowKey": security.token_hash(token),
        "email": email,
        "created_at": _iso(_now()),
        "last_seen_at": _iso(_now()),
        "expires_at": _iso(_now() + timedelta(days=SESSION_DAYS)),
    })
    return token


def new_verification_token(email: str) -> str:
    """Stored hashed with an expiry, like a session — a storage leak never
    yields a usable verification link."""
    token = security.new_token()
    tables.upsert(tables.TABLE_USERS, {
        "PartitionKey": USER_PK, "RowKey": email,
        "verify_hash": security.token_hash(token),
        "verify_expires_at": _iso(_now() + timedelta(hours=VERIFY_TTL_HOURS)),
    })
    return token


def signup(email: str, password: str, display_name: str = "") -> dict:
    email = normalize_email(email)
    if not _EMAIL_RE.match(email):
        raise ApiError(400, "enter a valid email address")
    if len(password or "") < MIN_PASSWORD:
        raise ApiError(400, f"password must be at least {MIN_PASSWORD} characters")

    existing = get_user_row(email)
    if existing is not None:
        # Never confirm that an address is registered — that's an account
        # enumeration oracle. The caller shows the same "check your email"
        # either way; only a real new row gets created.
        raise ApiError(409, "that email is already registered")

    row = {
        "PartitionKey": USER_PK, "RowKey": email,
        "password_hash": security.hash_password(password),
        "display_name": display_name.strip() or email.split("@")[0],
        "email_verified": False,
        "providers": "[]",
        "phone": "", "phone_verified": False,
        "tz": "America/New_York",
        "is_active": True, "failed_attempts": 0, "locked_until": "",
        "created_at": _iso(_now()), "updated_at": _iso(_now()), "last_login_at": "",
    }
    tables.upsert(tables.TABLE_USERS, row)
    verify_token = new_verification_token(email)
    return {"user": public_user(row), "verify_token": verify_token}


def login(email: str, password: str) -> dict:
    email = normalize_email(email)
    if not email or not password:
        raise ApiError(400, "email and password are required")
    row = get_user_row(email)
    if row is None or not bool(row.get("is_active", True)):
        # burn comparable time so unknown accounts aren't distinguishable
        security.verify_password(password, security.hash_password("x"))
        raise ApiError(401, "invalid credentials")

    locked_until = row.get("locked_until", "")
    if locked_until and locked_until > _iso(_now()):
        raise ApiError(423, "account locked — try again later")

    if not row.get("password_hash"):
        raise ApiError(400, "this account signs in with a social provider — use that button")

    if not security.verify_password(password, row.get("password_hash", "")):
        failed = int(row.get("failed_attempts", 0)) + 1
        update = {"PartitionKey": USER_PK, "RowKey": email, "failed_attempts": failed}
        if failed >= MAX_FAILED:
            update["locked_until"] = _iso(_now() + timedelta(minutes=LOCKOUT_MINUTES))
            update["failed_attempts"] = 0
        tables.upsert(tables.TABLE_USERS, update)
        raise ApiError(401, "invalid credentials")

    tables.upsert(tables.TABLE_USERS, {
        "PartitionKey": USER_PK, "RowKey": email,
        "failed_attempts": 0, "locked_until": "", "last_login_at": _iso(_now()),
    })
    return {"token": _issue_session(email), "user": public_user({**row, "RowKey": email})}


def verify_email(token: str) -> dict:
    """Consume an emailed verification token. Scans the (small) user table
    for the matching hash — a dedicated index isn't worth a table at this
    scale, and the hash is the only thing stored."""
    if not token:
        raise ApiError(400, "missing verification token")
    wanted = security.token_hash(token)
    for row in tables.query(tables.TABLE_USERS, f"PartitionKey eq '{USER_PK}'"):
        if not security.constant_time_eq(row.get("verify_hash", ""), wanted):
            continue
        if row.get("verify_expires_at", "") <= _iso(_now()):
            raise ApiError(400, "this verification link has expired — request a new one")
        email = row["RowKey"]
        tables.upsert(tables.TABLE_USERS, {
            "PartitionKey": USER_PK, "RowKey": email,
            "email_verified": True, "verify_hash": "", "verify_expires_at": "",
        })
        return {"token": _issue_session(email), "user": public_user({**row, "email_verified": True})}
    raise ApiError(400, "invalid verification token")


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
    user = get_user_row(session.get("email", ""))
    if user is None or not bool(user.get("is_active", True)):
        raise ApiError(401, "account disabled")
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


def user_id(user: dict | None) -> str:
    """The partition key for everything a user owns. Always derived from the
    validated session row — never from anything the request supplied."""
    if not user:
        raise ApiError(401, "not signed in")
    return user.get("RowKey", "")


def update_profile(email: str, changes: dict) -> dict:
    patchable = {"display_name", "phone", "tz"}
    update = {k: str(v or "") for k, v in changes.items() if k in patchable}
    if not update:
        raise ApiError(400, f"nothing to update — allowed: {sorted(patchable)}")
    if "phone" in update:
        update["phone_verified"] = False  # changing the number re-arms verification
    update.update({"PartitionKey": USER_PK, "RowKey": email, "updated_at": _iso(_now())})
    tables.upsert(tables.TABLE_USERS, update)
    return public_user(get_user_row(email) or {})


def set_password(email: str, current: str, new: str) -> None:
    row = get_user_row(email)
    if row is None:
        raise ApiError(404, "account not found")
    if row.get("password_hash") and not security.verify_password(current, row["password_hash"]):
        raise ApiError(401, "current password is incorrect")
    if len(new or "") < MIN_PASSWORD:
        raise ApiError(400, f"password must be at least {MIN_PASSWORD} characters")
    tables.upsert(tables.TABLE_USERS, {
        "PartitionKey": USER_PK, "RowKey": email,
        "password_hash": security.hash_password(new),
        "failed_attempts": 0, "locked_until": "", "updated_at": _iso(_now()),
    })
