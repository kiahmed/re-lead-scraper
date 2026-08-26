"""Per-user notes on a lead — the only content a public user may create.

PartitionKey is the user's id, taken from the validated session and never
from the request, so one user's partition is unreachable from another user's
token. `lead_id` is a column, which makes both access patterns one partition
query: "my notes on this lead" and "everything I've written" (the workspace
history).

RowKey = inverted-nanosecond tick + random suffix -> newest-first natural order,
the same scheme the admin API uses for interactions.
"""
import secrets
import time
from datetime import UTC, datetime

from . import tables
from .http import ApiError

MAX_BODY = 4000


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_row_key() -> str:
    return f"{(2**63 - 1) - time.time_ns():019d}-{secrets.token_hex(4)}"


def _public(row: dict) -> dict:
    return {
        "id": row.get("RowKey", ""),
        "lead_id": row.get("lead_id", ""),
        "body": row.get("body", ""),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
        "edited": bool(row.get("edited", False)),
    }


def _all_for_user(uid: str) -> list[dict]:
    rows = tables.query(tables.TABLE_NOTES, f"PartitionKey eq '{uid}'")
    return sorted(rows, key=lambda r: r.get("RowKey", ""))


def list_for_lead(uid: str, lead_id: str) -> list[dict]:
    return [_public(r) for r in _all_for_user(uid) if r.get("lead_id") == lead_id]


def list_all(uid: str) -> list[dict]:
    return [_public(r) for r in _all_for_user(uid)]


def counts_by_lead(uid: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in _all_for_user(uid):
        lead_id = row.get("lead_id", "")
        out[lead_id] = out.get(lead_id, 0) + 1
    return out


def create(uid: str, lead_id: str, payload: dict) -> dict:
    body = (payload.get("body") or "").strip()
    if not body:
        raise ApiError(400, "a note needs some text")
    if len(body) > MAX_BODY:
        raise ApiError(400, f"a note is limited to {MAX_BODY} characters")
    row = {
        "PartitionKey": uid,
        "RowKey": _new_row_key(),
        "lead_id": lead_id,
        "body": body,
        "created_at": _now(), "updated_at": _now(), "edited": False,
    }
    tables.upsert(tables.TABLE_NOTES, row)
    return _public(row)


def _own_note(uid: str, note_id: str) -> dict:
    row = tables.get_entity(tables.TABLE_NOTES, uid, note_id)
    if row is None:
        raise ApiError(404, "note not found")
    return row


def update(uid: str, note_id: str, payload: dict) -> dict:
    row = _own_note(uid, note_id)
    body = (payload.get("body") or "").strip()
    if not body:
        raise ApiError(400, "a note needs some text")
    if len(body) > MAX_BODY:
        raise ApiError(400, f"a note is limited to {MAX_BODY} characters")
    update = {
        "PartitionKey": uid, "RowKey": note_id,
        "body": body, "updated_at": _now(), "edited": True,
    }
    tables.upsert(tables.TABLE_NOTES, update)
    return _public({**row, **update})


def remove(uid: str, note_id: str) -> None:
    _own_note(uid, note_id)  # 404 rather than a silent no-op on someone else's id
    tables.delete(tables.TABLE_NOTES, uid, note_id)
