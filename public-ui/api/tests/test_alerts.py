import pytest

from core import alerts, tables
from core.http import ApiError


def test_create_and_list(make_user, alert_for):
    user = make_user()
    created = alert_for("buyer@example.com", user)
    assert created["name"] == "ATL SubTo"
    assert created["enabled"] is True
    assert [a["id"] for a in alerts.list_for_user("buyer@example.com")] == [created["id"]]


def test_a_new_alert_starts_from_now_not_from_the_backlog(make_user, alert_for):
    """Otherwise the first run dumps every stored lead on a new user."""
    user = make_user()
    created = alert_for("buyer@example.com", user)
    assert created["last_cursor"], "a new alert must carry a cursor"


def test_email_alerts_require_a_verified_address(make_user, alert_for):
    user = make_user("unverified@example.com", verified=False)
    with pytest.raises(ApiError) as e:
        alert_for("unverified@example.com", user)
    assert "verify your email" in e.value.message


def test_sms_alerts_require_a_phone_number(make_user, email_channel, monkeypatch):
    monkeypatch.setenv("NOTIFY_SMS_ENABLED", "true")
    monkeypatch.setenv("ACS_CONNECTION_STRING", "endpoint=https://x;accesskey=y")
    monkeypatch.setenv("ACS_SMS_FROM_NUMBER", "+18005551234")
    user = make_user("nophone@example.com")
    with pytest.raises(ApiError) as e:
        alerts.create("nophone@example.com", user, {
            "name": "texts", "criteria": {}, "channels": ["sms"],
        })
    assert "phone number" in e.value.message


def test_a_channel_that_is_switched_off_cannot_be_selected(make_user):
    user = make_user()
    with pytest.raises(ApiError) as e:
        alerts.create("buyer@example.com", user, {
            "name": "texts", "criteria": {}, "channels": ["sms"],
        })
    assert "not available" in e.value.message


def test_bad_criteria_is_refused_at_save_time(make_user, email_channel):
    user = make_user()
    with pytest.raises(ApiError):
        alerts.create("buyer@example.com", user, {
            "name": "broken", "channels": ["email"],
            "criteria": {"specs": [{"field": "nope", "op": "lte", "value": 1}]},
        })


def test_patching_one_field_keeps_the_rest(make_user, alert_for):
    user = make_user()
    created = alert_for("buyer@example.com", user)
    paused = alerts.update("buyer@example.com", created["id"], user, {"enabled": False})
    assert paused["enabled"] is False
    assert paused["name"] == "ATL SubTo"
    assert paused["criteria"] == {"categories": ["Subject-To"]}


def test_quiet_hours_and_cap_are_validated(make_user, alert_for):
    user = make_user()
    with pytest.raises(ApiError):
        alert_for("buyer@example.com", user, quiet_hours={"from": "9pm", "to": "08:00"})
    with pytest.raises(ApiError):
        alert_for("buyer@example.com", user, max_per_day=0)
    with pytest.raises(ApiError):
        alert_for("buyer@example.com", user, max_per_day=10_000)


def test_delete_removes_the_dedupe_log_too(make_user, alert_for):
    user = make_user()
    created = alert_for("buyer@example.com", user)
    tables.upsert(tables.TABLE_ALERTLOG, {
        "PartitionKey": created["id"], "RowKey": "lead-1", "lead_id": "lead-1",
    })
    alerts.remove("buyer@example.com", created["id"])
    assert alerts.list_for_user("buyer@example.com") == []
    assert tables.query(tables.TABLE_ALERTLOG, f"PartitionKey eq '{created['id']}'") == []


def test_one_user_cannot_touch_anothers_alert(make_user, alert_for):
    user = make_user()
    created = alert_for("buyer@example.com", user)
    with pytest.raises(ApiError) as e:
        alerts.get("mallory@example.com", created["id"])
    assert e.value.status == 404
    with pytest.raises(ApiError):
        alerts.update("mallory@example.com", created["id"], user, {"enabled": False})
    with pytest.raises(ApiError):
        alerts.remove("mallory@example.com", created["id"])


def test_preview_uses_the_same_matcher_as_the_notifier(make_user, make_lead, email_channel):
    make_lead("l1", category="Subject-To")
    make_lead("l2", category="Fix & Flip")
    result = alerts.preview({"criteria": {"categories": ["Subject-To"]}})
    assert result["total"] == 1
    assert result["items"][0]["id"] == "l1"


def test_alert_cap_per_user(make_user, alert_for):
    user = make_user()
    for _ in range(alerts.MAX_ALERTS_PER_USER):
        alert_for("buyer@example.com", user)
    with pytest.raises(ApiError) as e:
        alert_for("buyer@example.com", user)
    assert "delete one first" in e.value.message
