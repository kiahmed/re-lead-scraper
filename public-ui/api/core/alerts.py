"""Saved search criteria and their delivery settings.

An alert is one criteria object (see criteria.py) plus how and how often the
user wants to hear about matches. Partitioned by user id from the session,
like everything else a public user owns.
"""
import json
import re
import secrets
from datetime import UTC, datetime

from . import criteria, leads, notify, tables
from .http import ApiError

DIGESTS = ("instant", "hourly", "daily")
MAX_ALERTS_PER_USER = 25
DEFAULT_MAX_PER_DAY = 25
HARD_MAX_PER_DAY = 200
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _public(row: dict) -> dict:
    return {
        "id": row.get("RowKey", ""),
        "name": row.get("name", ""),
        "criteria": json.loads(row.get("criteria", "{}") or "{}"),
        "channels": json.loads(row.get("channels", "[]") or "[]"),
        "digest": row.get("digest", "instant"),
        "quiet_hours": json.loads(row.get("quiet_hours", "{}") or "{}"),
        "max_per_day": int(row.get("max_per_day", DEFAULT_MAX_PER_DAY)),
        "enabled": bool(row.get("enabled", True)),
        "last_cursor": row.get("last_cursor", ""),
        "last_fired_at": row.get("last_fired_at", ""),
        "sent_today": int(row.get("sent_today", 0)),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


def _validate(payload: dict, user: dict) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ApiError(400, "give the alert a name so you recognise it later")
    if len(name) > 80:
        raise ApiError(400, "alert names are limited to 80 characters")

    rules = criteria.validate(payload.get("criteria") or {})

    channels = payload.get("channels") or []
    if not isinstance(channels, list) or not channels:
        raise ApiError(400, "pick at least one way to be notified")
    for channel in channels:
        notify.assert_channel_available(channel)
    if "email" in channels and not bool(user.get("email_verified", False)):
        raise ApiError(400, "verify your email address before turning on email alerts")
    if "sms" in channels and not user.get("phone"):
        raise ApiError(400, "add a phone number in Settings before turning on text alerts")

    digest = payload.get("digest", "instant")
    if digest not in DIGESTS:
        raise ApiError(400, f"digest must be one of {list(DIGESTS)}")

    quiet = payload.get("quiet_hours") or {}
    if quiet:
        if not isinstance(quiet, dict):
            raise ApiError(400, "quiet_hours must be an object")
        for key in ("from", "to"):
            if quiet.get(key) and not _TIME_RE.match(str(quiet[key])):
                raise ApiError(400, f"quiet_hours.{key} must look like 21:00")

    try:
        max_per_day = int(payload.get("max_per_day", DEFAULT_MAX_PER_DAY))
    except (TypeError, ValueError):
        raise ApiError(400, "max_per_day must be a number") from None
    if not 1 <= max_per_day <= HARD_MAX_PER_DAY:
        raise ApiError(400, f"max_per_day must be between 1 and {HARD_MAX_PER_DAY}")

    return {
        "name": name,
        "criteria": json.dumps(rules),
        "channels": json.dumps(channels),
        "digest": digest,
        "quiet_hours": json.dumps(quiet),
        "max_per_day": max_per_day,
        "enabled": bool(payload.get("enabled", True)),
    }


def list_for_user(uid: str) -> list[dict]:
    rows = tables.query(tables.TABLE_ALERTS, f"PartitionKey eq '{uid}'")
    return sorted((_public(r) for r in rows), key=lambda a: a["created_at"])


def get(uid: str, alert_id: str) -> dict:
    row = tables.get_entity(tables.TABLE_ALERTS, uid, alert_id)
    if row is None:
        raise ApiError(404, "alert not found")
    return _public(row)


def create(uid: str, user: dict, payload: dict) -> dict:
    if len(list_for_user(uid)) >= MAX_ALERTS_PER_USER:
        raise ApiError(400, f"you can keep up to {MAX_ALERTS_PER_USER} alerts — delete one first")
    fields = _validate(payload, user)
    row = {
        "PartitionKey": uid,
        "RowKey": secrets.token_hex(8),
        # start from now: a new alert must not spam the user with the backlog
        "last_cursor": _now(),
        "last_fired_at": "", "sent_today": 0, "sent_day": "",
        "created_at": _now(), "updated_at": _now(),
        **fields,
    }
    tables.upsert(tables.TABLE_ALERTS, row)
    return _public(row)


def update(uid: str, alert_id: str, user: dict, payload: dict) -> dict:
    row = tables.get_entity(tables.TABLE_ALERTS, uid, alert_id)
    if row is None:
        raise ApiError(404, "alert not found")
    # a PATCH of just {"enabled": false} shouldn't have to resend the criteria
    merged = {**_public(row), **payload}
    fields = _validate(merged, user)
    update = {"PartitionKey": uid, "RowKey": alert_id, "updated_at": _now(), **fields}
    tables.upsert(tables.TABLE_ALERTS, update)
    return _public({**row, **update})


def remove(uid: str, alert_id: str) -> None:
    if tables.get_entity(tables.TABLE_ALERTS, uid, alert_id) is None:
        raise ApiError(404, "alert not found")
    for row in tables.query(tables.TABLE_ALERTLOG, f"PartitionKey eq '{alert_id}'"):
        tables.delete(tables.TABLE_ALERTLOG, alert_id, row["RowKey"])
    tables.delete(tables.TABLE_ALERTS, uid, alert_id)


def preview(payload: dict, limit: int = 20) -> dict:
    """Dry run: what would this criteria have matched, out of everything
    stored right now. Same matcher the notifier uses, so the preview is not
    an approximation of the alert — it IS the alert."""
    rules = criteria.validate(payload.get("criteria") or {})
    matched = criteria.filter_leads(leads.all_leads(), rules)
    return {
        "total": len(matched),
        "items": matched[:limit],
        # a rate an honest builder wants to see before saving
        "sample_window": {
            "oldest": matched[-1]["stored_at"] if matched else "",
            "newest": matched[0]["stored_at"] if matched else "",
        },
    }


def all_enabled() -> list[tuple[str, dict]]:
    """(user_id, alert) for every enabled alert — the notifier's work list."""
    rows = tables.scan(tables.TABLE_ALERTS)
    return [
        (r["PartitionKey"], _public(r))
        for r in rows
        if bool(r.get("enabled", True))
    ]


def record_send(uid: str, alert_id: str, cursor: str, sent: int, day: str) -> None:
    row = tables.get_entity(tables.TABLE_ALERTS, uid, alert_id) or {}
    already = int(row.get("sent_today", 0)) if row.get("sent_day") == day else 0
    tables.upsert(tables.TABLE_ALERTS, {
        "PartitionKey": uid, "RowKey": alert_id,
        "last_cursor": cursor or row.get("last_cursor", ""),
        "last_fired_at": _now(),
        "sent_today": already + sent,
        "sent_day": day,
    })


def sent_today(alert: dict, row_day: str, day: str) -> int:
    return alert["sent_today"] if row_day == day else 0


# ── web push subscriptions ───────────────────────────────────────────────────
def list_push(uid: str) -> list[dict]:
    rows = tables.query(tables.TABLE_PUSH, f"PartitionKey eq '{uid}'")
    return [
        {"id": r["RowKey"], "subscription": json.loads(r.get("subscription", "{}") or "{}"),
         "created_at": r.get("created_at", "")}
        for r in rows
    ]


def add_push(uid: str, subscription: dict) -> dict:
    endpoint = (subscription or {}).get("endpoint", "")
    if not endpoint:
        raise ApiError(400, "that push subscription is missing its endpoint")
    # keyed by the endpoint so re-subscribing the same browser updates in place
    rk = tables.encode_row_key(endpoint)[-200:]
    row = {
        "PartitionKey": uid, "RowKey": rk,
        "subscription": json.dumps(subscription),
        "created_at": _now(),
    }
    tables.upsert(tables.TABLE_PUSH, row)
    return {"id": rk}


def remove_push(uid: str, push_id: str) -> None:
    tables.delete(tables.TABLE_PUSH, uid, push_id)
