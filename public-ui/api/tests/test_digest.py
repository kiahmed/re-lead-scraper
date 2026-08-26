"""The notifier loop. Each test pins one of the guarantees the schedule
relies on, because a bug here is invisible until it wakes someone at 3am or
silently never fires at all."""
from datetime import UTC, datetime, timedelta

from core import alerts, digest, tables


def _rewind(uid, alert_id, days=30):
    """Alerts start with a cursor of 'now' so they never dump the backlog;
    tests rewind it to make stored leads look new."""
    tables.upsert(tables.TABLE_ALERTS, {
        "PartitionKey": uid, "RowKey": alert_id,
        "last_cursor": (datetime.now(UTC) - timedelta(days=days)).isoformat(),
    })


def _recent(hours=1):
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def test_a_matching_lead_is_delivered_once(make_user, make_lead, alert_for, sent_emails):
    user = make_user()
    alert = alert_for("buyer@example.com", user)
    _rewind("buyer@example.com", alert["id"])
    make_lead("l1", category="Subject-To", stored_at=_recent())

    report = digest.run()
    assert report["notified"] == 1
    assert len(sent_emails) == 1
    assert "1 new lead" in sent_emails[0]["subject"]

    # a second run must not resend it — dedupe by (alert, lead)
    assert digest.run()["notified"] == 0
    assert len(sent_emails) == 1


def test_non_matching_leads_are_left_alone(make_user, make_lead, alert_for, sent_emails):
    user = make_user()
    alert = alert_for("buyer@example.com", user)
    _rewind("buyer@example.com", alert["id"])
    make_lead("l1", category="Fix & Flip", stored_at=_recent())
    assert digest.run()["notified"] == 0
    assert sent_emails == []


def test_the_cursor_stops_the_backlog_flooding_a_new_alert(
    make_user, make_lead, alert_for, sent_emails
):
    user = make_user()
    make_lead("old", category="Subject-To", stored_at="2020-01-01T00:00:00+00:00")
    alert_for("buyer@example.com", user)   # cursor = now, no rewind
    assert digest.run()["notified"] == 0
    assert sent_emails == []


def test_a_dedupe_entry_survives_a_rewound_cursor(
    make_user, make_lead, alert_for, sent_emails
):
    user = make_user()
    alert = alert_for("buyer@example.com", user)
    _rewind("buyer@example.com", alert["id"])
    make_lead("l1", category="Subject-To", stored_at=_recent())
    digest.run()
    _rewind("buyer@example.com", alert["id"])   # operator rewinds by hand
    assert digest.run()["notified"] == 0        # still not resent


def test_quiet_hours_hold_rather_than_drop(
    make_user, make_lead, alert_for, sent_emails, monkeypatch
):
    user = make_user()
    alert = alert_for(
        "buyer@example.com", user,
        quiet_hours={"tz": "UTC", "from": "00:00", "to": "23:59"},
    )
    _rewind("buyer@example.com", alert["id"])
    make_lead("l1", category="Subject-To", stored_at=_recent())

    report = digest.run()
    assert report["notified"] == 0
    assert report["held_quiet"] == 1
    assert sent_emails == []

    # once quiet lifts, the held lead is still owed and goes out
    alerts.update("buyer@example.com", alert["id"], user, {"quiet_hours": {}})
    _rewind("buyer@example.com", alert["id"])
    assert digest.run()["notified"] == 1
    assert len(sent_emails) == 1


def test_quiet_window_wrapping_midnight():
    assert digest.in_quiet_hours({"tz": "UTC", "from": "00:00", "to": "23:59"}, "UTC")
    assert not digest.in_quiet_hours({}, "UTC")


def test_daily_cap_holds_the_remainder_and_says_so(
    make_user, make_lead, alert_for, sent_emails
):
    user = make_user()
    alert = alert_for("buyer@example.com", user, max_per_day=2)
    _rewind("buyer@example.com", alert["id"])
    for i in range(5):
        make_lead(f"l{i}", category="Subject-To", stored_at=_recent(hours=i + 1))

    report = digest.run()
    assert report["notified"] == 2
    assert report["held_cap"] == 3
    assert "held back" in sent_emails[0]["text"]
    assert "daily limit of 2" in sent_emails[0]["text"]


def test_a_disabled_alert_never_fires(make_user, make_lead, alert_for, sent_emails):
    user = make_user()
    alert = alert_for("buyer@example.com", user, enabled=False)
    _rewind("buyer@example.com", alert["id"])
    make_lead("l1", category="Subject-To", stored_at=_recent())
    assert digest.run()["notified"] == 0
    assert sent_emails == []


def test_a_disabled_account_never_fires(make_user, make_lead, alert_for, sent_emails):
    from core import auth
    user = make_user()
    alert = alert_for("buyer@example.com", user)
    _rewind("buyer@example.com", alert["id"])
    make_lead("l1", category="Subject-To", stored_at=_recent())
    tables.upsert(tables.TABLE_USERS, {
        "PartitionKey": auth.USER_PK, "RowKey": "buyer@example.com", "is_active": False,
    })
    assert digest.run()["notified"] == 0


def test_a_failing_channel_is_recorded_and_retried_not_swallowed(
    make_user, make_lead, alert_for, monkeypatch
):
    from core import notify
    user = make_user()
    alert = alert_for("buyer@example.com", user)
    _rewind("buyer@example.com", alert["id"])
    make_lead("l1", category="Subject-To", stored_at=_recent())

    def boom(*a, **k):
        raise notify.NotifyError("mailbox full")

    monkeypatch.setattr("core.digest.notify.send_email", boom)
    report = digest.run()
    assert report["notified"] == 0
    assert report["failures"] and "mailbox full" in report["failures"][0]["error"]
    # nothing was logged as sent, so the next run tries again
    assert tables.query(tables.TABLE_ALERTLOG, f"PartitionKey eq '{alert['id']}'") == []


def test_dry_run_reports_without_sending(make_user, make_lead, alert_for, sent_emails):
    user = make_user()
    alert = alert_for("buyer@example.com", user)
    _rewind("buyer@example.com", alert["id"])
    make_lead("l1", category="Subject-To", stored_at=_recent())
    report = digest.run(dry_run=True)
    assert report["dry_run"] is True
    assert report["notified"] == 1
    assert sent_emails == []


def test_the_message_carries_the_deal_numbers(make_user, make_lead, alert_for, sent_emails):
    user = make_user()
    alert = alert_for("buyer@example.com", user)
    _rewind("buyer@example.com", alert["id"])
    make_lead(
        "l1", category="Subject-To", stored_at=_recent(),
        content="Atlanta. Loan balance $185,000 at 4.25%. Asking 195k. No HOA.",
    )
    digest.run()
    text = sent_emails[0]["text"]
    assert "Subject-To" in text and "Atlanta" in text
    assert "$185,000" in text and "4.25%" in text


def test_hourly_digest_waits_for_its_interval(make_user, make_lead, alert_for, sent_emails):
    user = make_user()
    alert = alert_for("buyer@example.com", user, digest="hourly")
    _rewind("buyer@example.com", alert["id"])
    make_lead("l1", category="Subject-To", stored_at=_recent())
    assert digest.run()["notified"] == 1          # first run: nothing fired yet
    make_lead("l2", category="Subject-To", stored_at=_recent(hours=0))
    _rewind("buyer@example.com", alert["id"])
    assert digest.run()["notified"] == 0          # too soon to fire again
