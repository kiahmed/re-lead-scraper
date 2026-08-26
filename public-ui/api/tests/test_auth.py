import pytest

from core import auth, tables
from core.http import ApiError


def test_signup_creates_an_unverified_user_and_a_verification_token():
    result = auth.signup("New@Example.com ", "correct horse battery", "Newbie")
    assert result["user"]["email"] == "new@example.com"      # normalized
    assert result["user"]["email_verified"] is False
    assert result["verify_token"]
    row = auth.get_user_row("new@example.com")
    # only the hash is stored, never the token itself
    assert row["verify_hash"] and row["verify_hash"] != result["verify_token"]


def test_signup_rejects_a_duplicate_and_a_weak_password():
    auth.signup("a@example.com", "correct horse battery")
    with pytest.raises(ApiError) as e:
        auth.signup("a@example.com", "correct horse battery")
    assert e.value.status == 409
    with pytest.raises(ApiError):
        auth.signup("b@example.com", "short")
    with pytest.raises(ApiError):
        auth.signup("not-an-email", "correct horse battery")


def test_verification_round_trip_signs_the_user_in():
    result = auth.signup("v@example.com", "correct horse battery")
    verified = auth.verify_email(result["verify_token"])
    assert verified["user"]["email_verified"] is True
    assert auth.validate_token(verified["token"])["RowKey"] == "v@example.com"
    # single use — the token is cleared
    with pytest.raises(ApiError):
        auth.verify_email(result["verify_token"])


def test_login_happy_path_and_wrong_password(make_user):
    make_user("buyer@example.com")
    assert auth.login("buyer@example.com", "correct horse battery")["token"]
    with pytest.raises(ApiError) as e:
        auth.login("buyer@example.com", "wrong")
    assert e.value.status == 401


def test_unknown_user_is_indistinguishable_from_a_wrong_password():
    with pytest.raises(ApiError) as e:
        auth.login("ghost@example.com", "whatever")
    assert e.value.status == 401
    assert e.value.message == "invalid credentials"


def test_lockout_after_repeated_failures(make_user):
    make_user("locked@example.com")
    for _ in range(auth.MAX_FAILED):
        with pytest.raises(ApiError):
            auth.login("locked@example.com", "wrong")
    with pytest.raises(ApiError) as e:
        auth.login("locked@example.com", "correct horse battery")
    assert e.value.status == 423   # locked even with the RIGHT password


def test_social_only_account_is_told_to_use_the_button():
    tables.upsert(tables.TABLE_USERS, {
        "PartitionKey": auth.USER_PK, "RowKey": "social@example.com",
        "password_hash": "", "is_active": True, "email_verified": True,
    })
    with pytest.raises(ApiError) as e:
        auth.login("social@example.com", "anything")
    assert "social provider" in e.value.message


def test_session_validation_rejects_garbage_and_expired(make_user, token_for):
    make_user("s@example.com")
    token = token_for("s@example.com")
    assert auth.validate_token(token)["RowKey"] == "s@example.com"
    with pytest.raises(ApiError):
        auth.validate_token("not-a-real-token")
    auth.logout(token)
    with pytest.raises(ApiError):
        auth.validate_token(token)


def test_disabled_account_cannot_use_a_live_session(make_user, token_for):
    make_user("d@example.com")
    token = token_for("d@example.com")
    tables.upsert(tables.TABLE_USERS, {
        "PartitionKey": auth.USER_PK, "RowKey": "d@example.com", "is_active": False,
    })
    with pytest.raises(ApiError) as e:
        auth.validate_token(token)
    assert e.value.status == 401


def test_public_user_never_leaks_secrets(make_user):
    row = make_user("p@example.com")
    public = auth.public_user(row)
    assert "password_hash" not in public
    assert "verify_hash" not in public


def test_changing_the_phone_number_rearms_verification(make_user):
    make_user("ph@example.com", phone="+15551234567")
    updated = auth.update_profile("ph@example.com", {"phone": "+15559999999"})
    assert updated["phone"] == "+15559999999"
    assert updated["phone_verified"] is False
