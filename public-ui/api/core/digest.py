"""The notifier run: find new matches, respect the user's limits, deliver.

Called by the cron Logic App via POST /api/alerts/run (service token) and by
`make pub-run-alerts` on demand. Every guard lives here, so the schedule
carries no logic at all — exactly like the admin purge sweep.

Order of operations per alert, and why:
  1. cursor    — only leads stored since the last run are considered, so a
                 new alert never dumps the entire backlog on someone
  2. match     — criteria.match(), the same function the preview uses
  3. dedupe    — pubalertlog, keyed (alert_id, lead_id), so a rewound cursor
                 or a retried run cannot double-send
  4. quiet     — held, never dropped: the cursor does not advance past a lead
                 withheld for quiet hours, so it arrives when quiet lifts
  5. cap       — max_per_day, and the message says how many were held back
  6. deliver   — per channel, failures recorded and skipped, never fatal
"""
import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import alerts, auth, config, criteria, leads, notify, tables

MAX_LEADS_PER_MESSAGE = 10


def _now() -> datetime:
    return datetime.now(UTC)


def _user_now(tz_name: str) -> datetime:
    try:
        return _now().astimezone(ZoneInfo(tz_name or "America/New_York"))
    except (ZoneInfoNotFoundError, ValueError):
        return _now()


def in_quiet_hours(quiet: dict, tz_name: str) -> bool:
    """Windows that wrap midnight (21:00 -> 08:00) are the normal case, so
    handle them first-class rather than as an edge case."""
    start, end = (quiet or {}).get("from", ""), (quiet or {}).get("to", "")
    if not start or not end:
        return False
    now = _user_now(quiet.get("tz") or tz_name).strftime("%H:%M")
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def _due(alert: dict) -> bool:
    """Hourly/daily digests wait for their interval; instant is always due."""
    digest = alert.get("digest", "instant")
    if digest == "instant":
        return True
    last = alert.get("last_fired_at", "")
    if not last:
        return True
    try:
        since = _now() - datetime.fromisoformat(last)
    except ValueError:
        return True
    return since >= (timedelta(hours=1) if digest == "hourly" else timedelta(days=1))


def _already_sent(alert_id: str, lead_id: str) -> bool:
    rk = tables.encode_row_key(lead_id)
    return tables.get_entity(tables.TABLE_ALERTLOG, alert_id, rk) is not None


def _log_send(alert_id: str, lead_id: str, channels: list[str], outcome: str) -> None:
    tables.upsert(tables.TABLE_ALERTLOG, {
        "PartitionKey": alert_id,
        "RowKey": tables.encode_row_key(lead_id),
        "lead_id": lead_id,
        "channels": json.dumps(channels),
        "outcome": outcome,
        "sent_at": _now().isoformat(),
    })


# ── message rendering ────────────────────────────────────────────────────────
def _money(value) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


def _lead_line(lead: dict) -> str:
    bits = [lead.get("category") or "Unclassified"]
    if lead.get("cities"):
        bits.append(", ".join(lead["cities"]))
    specs = lead.get("specs") or {}
    for field, render in (
        ("asking_price", _money), ("loan_balance", _money),
        ("interest_rate", lambda v: f"{v}%"), ("monthly_payment", lambda v: f"{_money(v)}/mo"),
        ("ARV", lambda v: f"ARV {_money(v)}"),
    ):
        if field in specs:
            bits.append(render(specs[field]["value"]))
    return " · ".join(str(b) for b in bits)


def _render(alert: dict, matched: list[dict], held: int) -> tuple[str, str]:
    count = len(matched)
    subject = (
        f"{alert['name']}: {count} new lead{'s' if count != 1 else ''}"
        if count != 1 else f"{alert['name']}: 1 new lead"
    )
    site = config.site_url()
    lines = [f"{count} lead{'s' if count != 1 else ''} matched \"{alert['name']}\".", ""]
    for lead in matched[:MAX_LEADS_PER_MESSAGE]:
        lines.append(f"• {_lead_line(lead)}")
        snippet = (lead.get("snippet") or lead.get("content") or "").strip().replace("\n", " ")
        if snippet:
            lines.append(f"  {snippet[:160]}{'…' if len(snippet) > 160 else ''}")
        lines.append(f"  {site}/leads/{lead['id']}")
        lines.append("")
    if count > MAX_LEADS_PER_MESSAGE:
        lines.append(f"…and {count - MAX_LEADS_PER_MESSAGE} more — {site}/browse")
    if held:
        lines.append("")
        lines.append(
            f"{held} further match{'es' if held != 1 else ''} held back — you've hit this "
            f"alert's daily limit of {alert['max_per_day']}. Raise it in Settings."
        )
    lines += ["", f"Manage this alert: {site}/settings"]
    return subject, "\n".join(lines)


def _sms_text(alert: dict, matched: list[dict]) -> str:
    """SMS is charged per 160-character segment, so keep it to one where we
    can and always link out rather than inlining the post."""
    lead = matched[0]
    more = f" (+{len(matched) - 1} more)" if len(matched) > 1 else ""
    return f"{alert['name']}: {_lead_line(lead)}{more} — {config.site_url()}/browse"


# ── delivery ─────────────────────────────────────────────────────────────────
def _deliver(user_row: dict, uid: str, alert: dict, matched: list[dict], held: int) -> dict:
    subject, text = _render(alert, matched, held)
    outcomes: dict[str, str] = {}

    for channel in alert["channels"]:
        try:
            if channel == "email":
                if not bool(user_row.get("email_verified", False)):
                    raise notify.NotifyError("email address is not verified")
                notify.send_email(uid, subject, text)
            elif channel == "sms":
                notify.send_sms(user_row.get("phone", ""), _sms_text(alert, matched))
            elif channel == "webpush":
                subs = alerts.list_push(uid)
                if not subs:
                    raise notify.NotifyError("no browser is subscribed to push")
                delivered = 0
                for sub in subs:
                    try:
                        notify.send_webpush(
                            sub["subscription"], subject,
                            _lead_line(matched[0]), f"{config.site_url()}/browse",
                        )
                        delivered += 1
                    except notify.NotifyError as e:
                        # a browser that cleared its data is gone for good
                        if notify.push_is_gone(e):
                            alerts.remove_push(uid, sub["id"])
                        else:
                            raise
                if not delivered:
                    raise notify.NotifyError("every push subscription was stale")
            outcomes[channel] = "sent"
        except notify.NotifyError as e:
            # one dead channel must never abort the run for the others
            outcomes[channel] = f"failed: {e}"
    return outcomes


def run(limit_alerts: int = 0, dry_run: bool = False) -> dict:
    """Process every enabled alert. Returns a report the caller can log."""
    all_leads = leads.all_leads()
    report = {
        "dry_run": dry_run, "alerts_considered": 0, "alerts_fired": 0,
        "notified": 0, "held_quiet": 0, "held_cap": 0, "failures": [], "details": [],
    }

    work = alerts.all_enabled()
    if limit_alerts:
        work = work[:limit_alerts]

    for uid, alert in work:
        report["alerts_considered"] += 1
        if not _due(alert):
            continue

        user_row = auth.get_user_row(uid)
        if user_row is None or not bool(user_row.get("is_active", True)):
            continue

        cursor = alert.get("last_cursor", "")
        fresh = [ld for ld in all_leads if not cursor or ld.get("stored_at", "") > cursor]
        matched = criteria.filter_leads(fresh, alert["criteria"])
        matched = [ld for ld in matched if not _already_sent(alert["id"], ld["id"])]
        if not matched:
            continue

        # Quiet hours hold rather than drop: leave the cursor where it is so
        # everything withheld is picked up on the first run after quiet lifts.
        if in_quiet_hours(alert.get("quiet_hours") or {}, user_row.get("tz", "")):
            report["held_quiet"] += len(matched)
            report["details"].append({"alert": alert["name"], "outcome": "quiet hours"})
            continue

        day = _user_now(user_row.get("tz", "")).strftime("%Y-%m-%d")
        already = alerts.sent_today(alert, (
            tables.get_entity(tables.TABLE_ALERTS, uid, alert["id"]) or {}
        ).get("sent_day", ""), day)
        room = max(0, alert["max_per_day"] - already)
        if room == 0:
            report["held_cap"] += len(matched)
            report["details"].append({"alert": alert["name"], "outcome": "daily cap reached"})
            continue

        held = max(0, len(matched) - room)
        sending = matched[:room]
        report["held_cap"] += held

        if dry_run:
            report["alerts_fired"] += 1
            report["notified"] += len(sending)
            report["details"].append({
                "alert": alert["name"], "outcome": "would send", "leads": len(sending),
            })
            continue

        outcomes = _deliver(user_row, uid, alert, sending, held)
        succeeded = [c for c, o in outcomes.items() if o == "sent"]
        for channel, outcome in outcomes.items():
            if outcome != "sent":
                report["failures"].append({"alert": alert["name"], "channel": channel, "error": outcome})

        # Only record + advance when something actually went out; a run where
        # every channel failed must be retried, not silently swallowed.
        if succeeded:
            for lead in sending:
                _log_send(alert["id"], lead["id"], succeeded, "sent")
            newest = max(ld.get("stored_at", "") for ld in sending)
            # do not advance past leads held by the cap — they are still owed
            cursor_to = newest if not held else cursor
            alerts.record_send(uid, alert["id"], cursor_to, len(sending), day)
            report["alerts_fired"] += 1
            report["notified"] += len(sending)
            report["details"].append({
                "alert": alert["name"], "outcome": "sent",
                "leads": len(sending), "channels": succeeded,
            })
    return report


def send_test(uid: str, user_row: dict, alert: dict) -> dict:
    """One sample message on every channel the alert uses, so a user can
    prove the plumbing before trusting it."""
    sample = leads.all_leads()[:1]
    if not sample:
        sample = [{
            "id": "sample", "category": "Subject-To", "cities": ["Atlanta"],
            "specs": {}, "snippet": "This is a test — no leads are stored yet.",
            "stored_at": _now().isoformat(),
        }]
    return _deliver(user_row, uid, alert, sample, 0)
