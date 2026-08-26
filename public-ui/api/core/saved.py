"""The per-user workspace: which leads someone pinned, what state they put
them in, and their own tags. Partitioned by user id, like notes — a user's
workspace is unreachable with another user's token.

Nothing here touches the lead row itself; a "status" is this user's private
opinion about a lead, not a pipeline field.
"""
import json
from datetime import UTC, datetime

from . import tables
from .http import ApiError

STATUSES = ("new", "watching", "working", "passed")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _public(row: dict) -> dict:
    return {
        "lead_id": row.get("lead_id", ""),
        "pinned": bool(row.get("pinned", False)),
        "status": row.get("status", "new"),
        "tags": json.loads(row.get("tags", "[]") or "[]"),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


def list_for_user(uid: str) -> list[dict]:
    rows = tables.query(tables.TABLE_SAVED, f"PartitionKey eq '{uid}'")
    return sorted((_public(r) for r in rows), key=lambda e: e["updated_at"], reverse=True)


def get(uid: str, lead_id: str) -> dict | None:
    row = tables.get_entity(tables.TABLE_SAVED, uid, tables.encode_row_key(lead_id))
    return _public(row) if row else None


def put(uid: str, lead_id: str, payload: dict) -> dict:
    rk = tables.encode_row_key(lead_id)
    existing = tables.get_entity(tables.TABLE_SAVED, uid, rk) or {}

    status = payload.get("status", existing.get("status", "new"))
    if status not in STATUSES:
        raise ApiError(400, f"status must be one of {list(STATUSES)}")

    tags = payload.get("tags", json.loads(existing.get("tags", "[]") or "[]"))
    if not isinstance(tags, list):
        raise ApiError(400, "tags must be a list")
    tags = [str(t).strip()[:40] for t in tags if str(t).strip()][:20]

    row = {
        "PartitionKey": uid, "RowKey": rk,
        "lead_id": lead_id,
        "pinned": bool(payload.get("pinned", existing.get("pinned", False))),
        "status": status,
        "tags": json.dumps(tags),
        "created_at": existing.get("created_at", _now()),
        "updated_at": _now(),
    }
    tables.upsert(tables.TABLE_SAVED, row)
    return _public(row)


def remove(uid: str, lead_id: str) -> None:
    tables.delete(tables.TABLE_SAVED, uid, tables.encode_row_key(lead_id))
