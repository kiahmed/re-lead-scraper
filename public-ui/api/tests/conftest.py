import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import auth, security, tables  # noqa: E402
from tests.fakes import FakeProvider  # noqa: E402


@pytest.fixture(autouse=True)
def fake_tables():
    provider = FakeProvider()
    tables.set_provider(provider)
    yield provider
    tables.set_provider(None)


@pytest.fixture(autouse=True)
def offline_channels(monkeypatch):
    """Tests never touch a real mailer. Anything that tries is a bug in the
    test, not a network flake."""
    monkeypatch.setenv("NOTIFY_EMAIL_PROVIDER", "off")
    monkeypatch.setenv("NOTIFY_WEBPUSH_ENABLED", "false")
    monkeypatch.setenv("NOTIFY_SMS_ENABLED", "false")


@pytest.fixture
def make_user():
    def _make(email="buyer@example.com", verified=True, phone="", active=True):
        row = {
            "PartitionKey": auth.USER_PK, "RowKey": email,
            "password_hash": security.hash_password("correct horse battery"),
            "display_name": "Test Buyer",
            "email_verified": verified, "providers": "[]",
            "phone": phone, "phone_verified": bool(phone),
            "tz": "America/New_York", "is_active": active,
            "failed_attempts": 0, "locked_until": "",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "", "last_login_at": "",
        }
        tables.upsert(tables.TABLE_USERS, row)
        return row
    return _make


@pytest.fixture
def token_for():
    def _token(email):
        token = security.new_token()
        tables.upsert(tables.TABLE_SESSIONS, {
            "PartitionKey": auth.SESSION_PK,
            "RowKey": security.token_hash(token),
            "email": email,
            "created_at": datetime.now(UTC).isoformat(),
            "last_seen_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        })
        return token
    return _token


@pytest.fixture
def make_lead():
    """Writes straight to the fake leads table — the public API can only read
    it, which is the point."""
    def _make(lead_id="facebook_1", content="Atlanta. No HOA. Asking 195k.",
              category="Subject-To", stored_at="2026-08-20T12:00:00+00:00",
              is_complete=True, missing_fields=(), keywords=("Atlanta",)):
        tables.provider().get(tables.TABLE_LEADS).upsert_entity({
            "PartitionKey": "filtered",
            "RowKey": tables.encode_row_key(lead_id),
            "lead_id": lead_id, "content": content, "category": category,
            "keywords": json.dumps(list(keywords)),
            "is_complete": is_complete,
            "missing_fields": json.dumps(list(missing_fields)),
            "stored_at": stored_at, "authorName": "Seller", "groupName": "ATL REI",
            "extracted_info": json.dumps({"summary": "test"}),
        })
        return lead_id
    return _make


@pytest.fixture
def email_channel(monkeypatch):
    """Make the email channel *available* without making it *send* — enough
    config for validation to accept it, with the transport never invoked."""
    monkeypatch.setenv("NOTIFY_EMAIL_PROVIDER", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("NOTIFY_FROM_EMAIL", "alerts@example.com")


@pytest.fixture
def sent_emails(monkeypatch, email_channel):
    """Capture what would have gone out instead of hitting the network."""
    outbox: list[dict] = []

    def fake_send(to_address, subject, text, html=""):
        outbox.append({"to": to_address, "subject": subject, "text": text})

    monkeypatch.setattr("core.notify.send_email", fake_send)
    monkeypatch.setattr("core.digest.notify.send_email", fake_send)
    return outbox


@pytest.fixture
def alert_for(email_channel):
    from core import alerts

    def _make(uid, user, **over):
        payload = {
            "name": "ATL SubTo",
            "criteria": {"categories": ["Subject-To"]},
            "channels": ["email"],
            "digest": "instant",
            **over,
        }
        return alerts.create(uid, user, payload)
    return _make


def _iso_days_ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


@pytest.fixture
def days_ago():
    return _iso_days_ago
