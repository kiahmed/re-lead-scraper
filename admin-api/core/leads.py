"""Admin view over the pipeline's leads table.

Reads are unrestricted. Writes are limited to an explicit whitelist of
columns (user-directed edit feature) so pipeline-owned stage columns
(stored_at/classified_at/outreach_at, keywords, flags) can never be
clobbered from the UI. Delete removes the lead row AND its interactions.
"""
import json
from datetime import UTC, datetime, timedelta

from . import tables
from .http import ApiError

SNIPPET_CHARS = 280

# columns the UI may edit — everything else belongs to the pipeline
_EDITABLE_TEXT = {"category", "authorName", "groupName", "outreach_message", "investment_summary"}
_EDITABLE_JSON = {"contact", "extracted_info"}
_EDITABLE_BOOL = {"keep"}  # pinned leads are immune to purge


def _parse_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _to_lead(row: dict, full: bool = False) -> dict:
    content = row.get("content", "")
    lead = {
        "id": row.get("lead_id", "") or row.get("RowKey", ""),
        "authorName": row.get("authorName", ""),
        "groupName": row.get("groupName", ""),
        "keywords": _parse_json(row.get("keywords"), []),
        "category": row.get("category", ""),
        "has_selling_intent": row.get("has_selling_intent"),
        "is_complete": row.get("is_complete"),
        "outreach_skipped": row.get("outreach_skipped"),
        "keep": bool(row.get("keep", False)),
        "errorMessage": row.get("errorMessage", ""),
        "missing_fields": _parse_json(row.get("missing_fields"), []),
        "stored_at": row.get("stored_at", ""),
        "classified_at": row.get("classified_at", ""),
        "outreach_at": row.get("outreach_at", ""),
    }
    if full:
        lead.update({
            "url": row.get("url", ""),
            "content": content,
            "contact": _parse_json(row.get("contact"), {}),
            "extracted_info": _parse_json(row.get("extracted_info"), row.get("extracted_info", "")),
            "outreach_message": row.get("outreach_message", ""),
            "investment_summary": row.get("investment_summary", ""),
            "location_insights": _parse_json(row.get("location_insights"), {}),
        })
    else:
        lead["snippet"] = content[:SNIPPET_CHARS] + ("…" if len(content) > SNIPPET_CHARS else "")
    return lead


def _matches(lead: dict, category: str, is_complete: str, q: str) -> bool:
    if category and lead["category"] != category:
        return False
    if is_complete in ("true", "false") and lead["is_complete"] is not None:
        if bool(lead["is_complete"]) != (is_complete == "true"):
            return False
    elif is_complete in ("true", "false"):
        return False
    if q:
        hay = " ".join([
            lead.get("snippet", ""), lead.get("content", ""),
            lead["authorName"], lead["groupName"], " ".join(lead["keywords"]),
        ]).lower()
        if q.lower() not in hay:
            return False
    return True


def _parse_dt(value: str) -> datetime | None:
    """Accept full ISO datetimes ('Z' or offset) and bare dates."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, f"invalid date filter: {value}") from None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _in_date_range(lead: dict, dt_from: datetime | None, dt_to: datetime | None) -> bool:
    if dt_from is None and dt_to is None:
        return True
    stored = _parse_dt_or_none(lead.get("stored_at", ""))
    if stored is None:
        return False
    if dt_from is not None and stored < dt_from:
        return False
    if dt_to is not None and stored > dt_to:
        return False
    return True


def _parse_dt_or_none(value: str) -> datetime | None:
    try:
        return _parse_dt(value)
    except ApiError:
        return None


def list_leads(query: dict) -> dict:
    rows = tables.query(tables.TABLE_LEADS, "PartitionKey eq 'filtered'")
    all_leads = sorted(
        (_to_lead(r) for r in rows),
        key=lambda ld: ld["stored_at"], reverse=True,
    )
    category = query.get("category", "")
    is_complete = query.get("is_complete", "")
    q = query.get("q", "")
    dt_from = _parse_dt(query.get("from", ""))
    dt_to = _parse_dt(query.get("to", ""))
    if dt_to is not None and "T" not in query.get("to", ""):
        dt_to = dt_to + timedelta(days=1)  # bare date → inclusive end of day

    # counts by category over the search/date-filtered (but not
    # category-filtered) set, so the category tabs always show what's behind them
    searched = [
        ld for ld in all_leads
        if _matches(ld, "", is_complete, q) and _in_date_range(ld, dt_from, dt_to)
    ]
    counts: dict[str, int] = {}
    for lead in searched:
        counts[lead["category"] or "Unclassified"] = counts.get(lead["category"] or "Unclassified", 0) + 1

    filtered = [ld for ld in searched if _matches(ld, category, "", "")]
    try:
        page = max(1, int(query.get("page", 1)))
        page_size = min(100, max(1, int(query.get("pageSize", 25))))
    except ValueError:
        raise ApiError(400, "page and pageSize must be integers") from None
    start = (page - 1) * page_size
    return {
        "items": filtered[start:start + page_size],
        "total": len(filtered),
        "page": page,
        "pageSize": page_size,
        "counts": counts,
    }


def _find_row(lead_id: str) -> tuple[str, dict]:
    """The leads table mixes two RowKey schemes: the local pipeline stores
    quote(lead_id) but the hub Logic App stores the raw id (legal in Azure
    Tables). Try both; return (rowkey, row) or raise 404."""
    for rk in (tables.encode_row_key(lead_id), lead_id):
        row = tables.get_entity(tables.TABLE_LEADS, "filtered", rk)
        if row is not None:
            return rk, row
    raise ApiError(404, "lead not found")


def get_lead(lead_id: str) -> dict:
    _, row = _find_row(lead_id)
    return _to_lead(row, full=True)


def update_lead(lead_id: str, changes: dict) -> dict:
    rk, _ = _find_row(lead_id)
    update: dict = {}
    for key, value in changes.items():
        if key in _EDITABLE_TEXT:
            update[key] = "" if value is None else str(value)
        elif key in _EDITABLE_JSON:
            update[key] = json.dumps(value) if isinstance(value, (dict, list)) else str(value or "")
        elif key in _EDITABLE_BOOL:
            update[key] = bool(value)
    if not update:
        editable = sorted(_EDITABLE_TEXT | _EDITABLE_JSON | _EDITABLE_BOOL)
        raise ApiError(400, f"nothing to update — editable: {editable}")
    update.update({"PartitionKey": "filtered", "RowKey": rk})
    tables.upsert(tables.TABLE_LEADS, update)
    return get_lead(lead_id)


def delete_lead(lead_id: str) -> None:
    rk, _ = _find_row(lead_id)
    # interactions are always keyed by the encoded id, independent of which
    # RowKey scheme the lead row itself uses
    ipk = tables.encode_row_key(lead_id)
    for row in tables.query(tables.TABLE_INTERACTIONS, f"PartitionKey eq '{ipk}'"):
        tables.delete(tables.TABLE_INTERACTIONS, ipk, row["RowKey"])
    tables.delete(tables.TABLE_LEADS, "filtered", rk)


def purge_leads(params: dict) -> dict:
    """Bulk-delete leads received in a date window, with two protections:
    leads pinned with keep=true are never purged, and leads that have notes
    or follow-ups are skipped unless include_worked is set. dry_run (the
    default) only counts."""
    to_raw = str(params.get("to", ""))
    dt_from = _parse_dt(str(params.get("from", "")))
    dt_to = _parse_dt(to_raw)
    if dt_to is None:
        raise ApiError(400, "a 'to' date is required — refusing an unbounded purge")
    if "T" not in to_raw:
        dt_to = dt_to + timedelta(days=1)  # bare date → inclusive end of day
    include_worked = bool(params.get("include_worked", False))
    dry_run = bool(params.get("dry_run", True))
    categories = params.get("categories")  # None/[] = all; names use "Unclassified" for blank
    if categories is not None and not isinstance(categories, list):
        raise ApiError(400, "categories must be a list")

    rows = tables.query(tables.TABLE_LEADS, "PartitionKey eq 'filtered'")
    to_purge: list[dict] = []
    skipped_keep = skipped_activity = skipped_undated = 0
    by_category: dict[str, int] = {}
    all_dates: list[str] = []
    matched_dates: list[str] = []
    for row in rows:
        lead = _to_lead(row)
        stored = lead.get("stored_at", "")
        has_date = _parse_dt_or_none(stored) is not None
        if has_date:
            all_dates.append(stored)
        if categories and (lead["category"] or "Unclassified") not in categories:
            continue
        if not has_date:
            skipped_undated += 1  # no timestamp — age unknown, never purged by date
            continue
        if not _in_date_range(lead, dt_from, dt_to):
            continue
        if bool(row.get("keep", False)):
            skipped_keep += 1
            continue
        lead_id = row.get("lead_id", "") or row.get("RowKey", "")
        ipk = tables.encode_row_key(lead_id)
        interactions = tables.query(tables.TABLE_INTERACTIONS, f"PartitionKey eq '{ipk}'")
        if interactions and not include_worked:
            skipped_activity += 1
            continue
        to_purge.append({"row": row, "ipk": ipk, "interactions": interactions})
        matched_dates.append(stored)
        cat = lead["category"] or "Unclassified"
        by_category[cat] = by_category.get(cat, 0) + 1

    if not dry_run:
        for entry in to_purge:
            for i_row in entry["interactions"]:
                tables.delete(tables.TABLE_INTERACTIONS, entry["ipk"], i_row["RowKey"])
            tables.delete(tables.TABLE_LEADS, "filtered", entry["row"]["RowKey"])

    return {
        "dry_run": dry_run,
        "matched": len(to_purge) + skipped_keep + skipped_activity,
        "purged": 0 if dry_run else len(to_purge),
        "would_purge": len(to_purge),
        "skipped_keep": skipped_keep,
        "skipped_activity": skipped_activity,
        "skipped_undated": skipped_undated,
        # spans let the UI show the real window it just previewed, and explain
        # an empty result ("your oldest lead is only N days old")
        "matched_span": {
            "oldest": min(matched_dates) if matched_dates else "",
            "newest": max(matched_dates) if matched_dates else "",
        },
        "data_span": {
            "oldest": min(all_dates) if all_dates else "",
            "newest": max(all_dates) if all_dates else "",
        },
        "by_category": by_category,
    }


def purge_by_ttl(params: dict) -> dict:
    """Scheduled-sweep mode: per-category TTLs in days. Reuses purge_leads
    per category so every protection (keep pin, activity skip) applies."""
    ttl_days = params.get("ttl_days")
    if not isinstance(ttl_days, dict) or not ttl_days:
        raise ApiError(400, "ttl_days must be a non-empty object of {category: days}")
    dry_run = bool(params.get("dry_run", True))
    include_worked = bool(params.get("include_worked", False))
    now = datetime.now(UTC)
    per_category: dict[str, dict] = {}
    totals = {"purged": 0, "would_purge": 0, "skipped_keep": 0, "skipped_activity": 0}
    for category, days in ttl_days.items():
        try:
            cutoff = (now - timedelta(days=int(days))).isoformat()
        except (TypeError, ValueError):
            raise ApiError(400, f"ttl_days for {category} must be an integer") from None
        result = purge_leads({
            "to": cutoff, "categories": [category],
            "dry_run": dry_run, "include_worked": include_worked,
        })
        per_category[category] = {"cutoff": cutoff, **{k: result[k] for k in totals}}
        for k in totals:
            totals[k] += result[k]
    return {"dry_run": dry_run, "mode": "ttl", **totals, "per_category": per_category}
