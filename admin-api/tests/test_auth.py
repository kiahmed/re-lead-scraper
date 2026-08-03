from datetime import UTC, datetime, timedelta

import pytest

from core import auth, tables, users
from core.http import ApiError


@pytest.fixture
def alice():
    return users.create_user("Alice", "correct-horse", display_name="Alice A")


def test_login_success_returns_token_and_user(alice):
    result = auth.login("alice", "correct-horse")
    assert result["user"]["username"] == "alice"
    assert result["token"]
    # session row stores only the hash, never the token
    sessions = tables.query(tables.TABLE_SESSIONS, "PartitionKey eq 'session'")
    assert len(sessions) == 1
    assert result["token"] not in str(sessions[0])


def test_login_wrong_password_401(alice):
    with pytest.raises(ApiError) as e:
        auth.login("alice", "wrong")
    assert e.value.status == 401


def test_unknown_user_401():
    with pytest.raises(ApiError) as e:
        auth.login("nobody", "whatever")
    assert e.value.status == 401


def test_lockout_after_five_failures(alice):
    for _ in range(5):
        with pytest.raises(ApiError):
            auth.login("alice", "wrong")
    with pytest.raises(ApiError) as e:
        auth.login("alice", "correct-horse")  # correct password, but locked
    assert e.value.status == 423


def test_counter_resets_on_success(alice):
    for _ in range(4):
        with pytest.raises(ApiError):
            auth.login("alice", "wrong")
    auth.login("alice", "correct-horse")
    row = tables.get_entity(tables.TABLE_USERS, "user", "alice")
    assert int(row["failed_attempts"]) == 0


def test_validate_token_roundtrip(alice):
    token = auth.login("alice", "correct-horse")["token"]
    user = auth.validate_token(token)
    assert user["RowKey"] == "alice"


def test_validate_rejects_bad_and_missing_token(alice):
    with pytest.raises(ApiError):
        auth.validate_token("")
    with pytest.raises(ApiError):
        auth.validate_token("forged-token")


def test_expired_session_rejected_and_deleted(alice):
    token = auth.login("alice", "correct-horse")["token"]
    from core import security
    rk = security.token_hash(token)
    tables.upsert(tables.TABLE_SESSIONS, {
        "PartitionKey": "session", "RowKey": rk,
        "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
    })
    with pytest.raises(ApiError) as e:
        auth.validate_token(token)
    assert e.value.status == 401
    assert tables.get_entity(tables.TABLE_SESSIONS, "session", rk) is None


def test_disabled_user_cannot_login_or_use_session(alice):
    token = auth.login("alice", "correct-horse")["token"]
    users.set_active("alice", False)
    with pytest.raises(ApiError):
        auth.validate_token(token)
    with pytest.raises(ApiError):
        auth.login("alice", "correct-horse")


def test_logout_revokes_session(alice):
    token = auth.login("alice", "correct-horse")["token"]
    auth.logout(token)
    with pytest.raises(ApiError):
        auth.validate_token(token)


def test_new_token_each_login_no_fixation(alice):
    t1 = auth.login("alice", "correct-horse")["token"]
    t2 = auth.login("alice", "correct-horse")["token"]
    assert t1 != t2
