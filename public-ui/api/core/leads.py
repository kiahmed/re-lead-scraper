"""Read-only public view over the pipeline's leads table.

There is no write path in this module and no write route in routes.py — the
public app cannot edit or delete a lead, by construction rather than by policy.
Per-user data (notes, workspace, alerts) lives in the pub* tables instead.
"""
import json
from datetime import UTC, datetime, timedelta

from . import leadfilter, specs, tables
from .http import ApiError

SNIPPET_CHARS = 280


def as_bool(value):
    """The pipeline writes is_complete two ways: the local runner stores a real
    boolean, the hub/spoke Logic Apps store the STRING "True"/"False" (their
    table bodies interpolate "@{...}"). bool("False") is True, so passing the
    raw value through marks every Logic-App-written incomplete lead complete.
    Returns None when the value is genuinely absent."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1"):
            return True
        if lowered in ("false", "0"):
            return False
        return None
    return bool(value)


def _parse_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def to_lead(row: dict, full: bool = False) -> dict:
    """Shared shape for list rows, detail, and alert matching — so an alert
    preview and the browse list are looking at literally the same object."""
    content = row.get("content", "")
    keywords = _parse_json(row.get("keywords"), [])
    cities = leadfilter.detect_cities(content, keywords)
    extracted = _parse_json(row.get("extracted_info"), row.get("extracted_info", ""))
    lead = {
        "id": row.get("lead_id", "") or row.get("RowKey", ""),
        "authorName": row.get("authorName", ""),
        "groupName": row.get("groupName", ""),
        "keywords": keywords,
        "category": row.get("category", ""),
        "has_selling_intent": as_bool(row.get("has_selling_intent")),
        "is_complete": as_bool(row.get("is_complete")),
        "cities": cities,
        "hoa": leadfilter.hoa_state(content, keywords),
        "missing_fields": _parse_json(row.get("missing_fields"), []),
        "stored_at": row.get("stored_at", ""),
        "classified_at": row.get("classified_at", ""),
        "outreach_at": row.get("outreach_at", ""),
    }
    lead["specs"] = specs.extract(content, extracted, cities)
    if full:
        lead.update({
            "url": row.get("url", ""),
            "content": content,
            "extracted_info": extracted,
            "outreach_message": row.get("outreach_message", ""),
            "investment_summary": row.get("investment_summary", ""),
            "location_insights": _parse_json(row.get("location_insights"), {}),
        })
    else:
        lead["snippet"] = content[:SNIPPET_CHARS] + ("…" if len(content) > SNIPPET_CHARS else "")
    return lead


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, f"invalid date filter: {value}") from None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _parse_dt_or_none(value: str) -> datetime | None:
    try:
        return _parse_dt(value)
    except ApiError:
        return None


def all_leads() -> list[dict]:
    """Every filtered lead, newest first. One table scan; the alert notifier
    and the browse list share it."""
    rows = tables.query(tables.TABLE_LEADS, "PartitionKey eq 'filtered'")
    return sorted((to_lead(r) for r in rows), key=lambda ld: ld["stored_at"], reverse=True)


def _predicates(query: dict, dt_from, dt_to) -> dict:
    """One predicate per dimension so each facet's counts can be computed with
    its own filter left out — proper faceting, same as the admin list."""
    category = query.get("category", "")
    is_complete = query.get("is_complete", "")
    q = (query.get("q", "") or "").lower()
    city = query.get("city", "")
    hoa = query.get("hoa", "")

    def by_category(ld):
        return not category or (ld["category"] or "Unclassified") == category

    def by_complete(ld):
        if is_complete not in ("true", "false"):
            return True
        if ld["is_complete"] is None:
            return False
        # already coerced by to_lead — never re-bool() a raw table value here
        return ld["is_complete"] == (is_complete == "true")

    def by_text(ld):
        if not q:
            return True
        hay = " ".join([
            ld.get("snippet", ""), ld.get("content", ""),
            ld["authorName"], ld["groupName"], " ".join(ld["keywords"]),
        ]).lower()
        return q in hay

    def by_date(ld):
        if dt_from is None and dt_to is None:
            return True
        stored = _parse_dt_or_none(ld.get("stored_at", ""))
        if stored is None:
            return False
        if dt_from is not None and stored < dt_from:
            return False
        return not (dt_to is not None and stored > dt_to)

    def by_city(ld):
        return leadfilter.matches_city(ld["cities"], city)

    def by_hoa(ld):
        return not hoa or ld["hoa"] == hoa

    return {
        "category": by_category, "is_complete": by_complete, "q": by_text,
        "date": by_date, "city": by_city, "hoa": by_hoa,
    }


def list_leads(query: dict) -> dict:
    all_ = all_leads()
    to_raw = query.get("to", "")
    dt_from = _parse_dt(query.get("from", ""))
    dt_to = _parse_dt(to_raw)
    if dt_to is not None and "T" not in to_raw:
        dt_to = dt_to + timedelta(days=1)  # bare date -> inclusive end of day

    preds = _predicates(query, dt_from, dt_to)

    def subset(exclude: str | None):
        return [ld for ld in all_ if all(p(ld) for n, p in preds.items() if n != exclude)]

    def tally(leads, key):
        out: dict[str, int] = {}
        for ld in leads:
            for value in key(ld):
                out[value] = out.get(value, 0) + 1
        return out

    filtered = subset(None)
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
        "counts": tally(subset("category"), lambda ld: [ld["category"] or "Unclassified"]),
        "city_counts": tally(subset("city"), lambda ld: ld["cities"] or [leadfilter.OTHER_CITY]),
        "hoa_counts": tally(subset("hoa"), lambda ld: [ld["hoa"]]),
    }


def get_lead(lead_id: str) -> dict:
    """The leads table mixes two RowKey schemes: the local pipeline stores
    quote(lead_id) but the hub Logic App stores the raw id (legal in Azure
    Tables). Try both."""
    for rk in (tables.encode_row_key(lead_id), lead_id):
        row = tables.get_entity(tables.TABLE_LEADS, "filtered", rk)
        if row is not None:
            return to_lead(row, full=True)
    raise ApiError(404, "lead not found")
