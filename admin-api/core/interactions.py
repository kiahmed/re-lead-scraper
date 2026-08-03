"""Notes / follow-ups / message-status per lead.

PartitionKey = the lead's encoded row key (one partition per lead).
RowKey = inverted-nanosecond tick + random suffix → newest-first natural order.
"""
import secrets
import time
from datetime import UTC, datetime

from . import tables
from .http import ApiError

TYPES = {"note", "message_out", "follow_up", "status_change"}
_PATCHABLE = {"body", "status", "follow_up_at", "follow_up_done"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_row_key() -> str:
    return f"{(2**63 - 1) - time.time_ns():019d}-{secrets.token_hex(4)}"


def _public(row: dict) -> dict:
    return {
        "id": row.get("RowKey", ""),
        "type": row.get("type", "note"),
        "body": row.get("body", ""),
        "author": row.get("author", ""),
        "channel": row.get("channel", ""),
        "status": row.get("status", ""),
        "follow_up_at": row.get("follow_up_at", ""),
        "follow_up_done": bool(row.get("follow_up_done", False)),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
        "edited": bool(row.get("edited", False)),
    }


def list_for_lead(lead_id: str) -> list[dict]:
    pk = tables.encode_row_key(lead_id)
    rows = tables.query(tables.TABLE_INTERACTIONS, f"PartitionKey eq '{pk}'")
    return [_public(r) for r in sorted(rows, key=lambda r: r.get("RowKey", ""))]


def create(lead_id: str, author: str, payload: dict) -> dict:
    itype = payload.get("type", "note")
    if itype not in TYPES:
        raise ApiError(400, f"type must be one of {sorted(TYPES)}")
    body = (payload.get("body") or "").strip()
    if not body and itype != "status_change":
        raise ApiError(400, "body is required")
    row = {
        "PartitionKey": tables.encode_row_key(lead_id),
        "RowKey": _new_row_key(),
        "type": itype,
        "body": body,
        "author": author,
        "channel": payload.get("channel", "manual"),
        "status": payload.get("status", ""),
        "follow_up_at": payload.get("follow_up_at", ""),
        "follow_up_done": False,
        "created_at": _now(), "updated_at": _now(), "edited": False,
    }
    tables.upsert(tables.TABLE_INTERACTIONS, row)
    return _public(row)


def patch(lead_id: str, interaction_id: str, changes: dict) -> dict:
    pk = tables.encode_row_key(lead_id)
    row = tables.get_entity(tables.TABLE_INTERACTIONS, pk, interaction_id)
    if row is None:
        raise ApiError(404, "interaction not found")
    update = {k: v for k, v in changes.items() if k in _PATCHABLE}
    if not update:
        raise ApiError(400, f"nothing to update — allowed: {sorted(_PATCHABLE)}")
    update.update({
        "PartitionKey": pk, "RowKey": interaction_id,
        "updated_at": _now(), "edited": "body" in update or bool(row.get("edited")),
    })
    tables.upsert(tables.TABLE_INTERACTIONS, update)
    return _public({**row, **update})


def remove(lead_id: str, interaction_id: str) -> None:
    tables.delete(tables.TABLE_INTERACTIONS, tables.encode_row_key(lead_id), interaction_id)
