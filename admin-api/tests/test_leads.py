import json

import pytest

from core import leads, tables
from core.http import ApiError


def seed_lead(i: int, category="Subject-To", complete=True, content=None, author="Maria"):
    lead_id = f"facebook_lead+{i}=="
    tables.upsert(tables.TABLE_LEADS, {
        "PartitionKey": "filtered",
        "RowKey": tables.encode_row_key(lead_id),
        "lead_id": lead_id,
        "content": content or f"Selling my Atlanta property number {i}, needs work",
        "keywords": json.dumps(["Atlanta"]),
        "authorName": f"{author} {i}",
        "groupName": "ATL Wholesalers",
        "category": category,
        "is_complete": complete,
        "contact": json.dumps({"author": author, "dm_requested": True}),
        "extracted_info": json.dumps({"loan_balance": 210000}),
        "location_insights": json.dumps({"crime_index": "moderate"}),
        "missing_fields": json.dumps([] if complete else ["asking_price"]),
        "outreach_message": "Hey!",
        "stored_at": f"2026-08-01T09:{i:02d}:00+00:00",
    })
    return lead_id


def test_list_sorted_newest_first_with_snippet():
    seed_lead(1)
    seed_lead(2)
    result = leads.list_leads({})
    assert result["total"] == 2
    assert result["items"][0]["stored_at"] > result["items"][1]["stored_at"]
    assert "snippet" in result["items"][0]
    assert "content" not in result["items"][0]


def test_category_filter_and_counts():
    seed_lead(1, category="Subject-To")
    seed_lead(2, category="Fix & Flip")
    seed_lead(3, category="Fix & Flip")
    result = leads.list_leads({"category": "Fix & Flip"})
    assert result["total"] == 2
    # counts ignore the category filter so tabs stay populated
    assert result["counts"] == {"Subject-To": 1, "Fix & Flip": 2}


def test_completeness_and_text_filters():
    seed_lead(1, complete=True)
    seed_lead(2, complete=False, content="Jacksonville duplex for sale")
    assert leads.list_leads({"is_complete": "false"})["total"] == 1
    assert leads.list_leads({"q": "jacksonville"})["total"] == 1
    assert leads.list_leads({"q": "zzz-no-match"})["total"] == 0


def test_pagination():
    for i in range(7):
        seed_lead(i)
    result = leads.list_leads({"page": "2", "pageSize": "3"})
    assert result["total"] == 7
    assert len(result["items"]) == 3
    with pytest.raises(ApiError):
        leads.list_leads({"page": "x"})


def test_get_lead_full_shape_and_json_parsing():
    lead_id = seed_lead(1)
    lead = leads.get_lead(lead_id)
    assert lead["content"].startswith("Selling my Atlanta")
    assert lead["contact"]["dm_requested"] is True
    assert lead["extracted_info"] == {"loan_balance": 210000}
    assert lead["location_insights"] == {"crime_index": "moderate"}


def test_get_lead_tolerates_malformed_json_columns():
    lead_id = seed_lead(1)
    tables.upsert(tables.TABLE_LEADS, {
        "PartitionKey": "filtered",
        "RowKey": tables.encode_row_key(lead_id),
        "extracted_info": "not-json{{{",
        "contact": "",
    })
    lead = leads.get_lead(lead_id)
    assert lead["extracted_info"] == "not-json{{{"  # falls back to raw string
    assert lead["contact"] == {}


def test_get_missing_lead_404():
    with pytest.raises(ApiError) as e:
        leads.get_lead("nope")
    assert e.value.status == 404


def test_update_lead_whitelist():
    lead_id = seed_lead(1)
    updated = leads.update_lead(lead_id, {
        "category": "Seller Finance",
        "contact": {"author": "Maria", "phone": "555-0100"},
        "extracted_info": {"loan_balance": 200000},
        "outreach_message": "edited msg",
        "stored_at": "2020-01-01",          # pipeline column — must be ignored
        "is_complete": False,               # pipeline column — must be ignored
    })
    assert updated["category"] == "Seller Finance"
    assert updated["contact"]["phone"] == "555-0100"
    assert updated["extracted_info"] == {"loan_balance": 200000}
    assert updated["outreach_message"] == "edited msg"
    assert updated["stored_at"] == "2026-08-01T09:01:00+00:00"  # untouched
    assert updated["is_complete"] is True  # untouched


def test_update_lead_rejects_empty_and_missing():
    lead_id = seed_lead(1)
    with pytest.raises(ApiError):
        leads.update_lead(lead_id, {"stored_at": "2020-01-01"})
    with pytest.raises(ApiError):
        leads.update_lead("nope", {"category": "Hybrid"})


def test_delete_lead_removes_row_and_interactions():
    from core import interactions
    lead_id = seed_lead(1)
    interactions.create(lead_id, "alice", {"type": "note", "body": "will vanish"})
    leads.delete_lead(lead_id)
    with pytest.raises(ApiError):
        leads.get_lead(lead_id)
    assert interactions.list_for_lead(lead_id) == []
    with pytest.raises(ApiError):
        leads.delete_lead(lead_id)  # already gone → 404


def test_hub_written_rows_use_raw_rowkey():
    """The hub Logic App stores the RAW lead id as RowKey (no url-encoding);
    lookup, update, and delete must resolve both schemes."""
    lead_id = "facebook_hubrow+9=="
    tables.upsert(tables.TABLE_LEADS, {
        "PartitionKey": "filtered",
        "RowKey": lead_id,                      # raw — as the hub writes it
        "lead_id": lead_id,
        "content": "hub-written row",
        "keywords": json.dumps([]),
        "category": "Seller Finance",
        "stored_at": "2026-08-01T10:00:00+00:00",
    })
    assert leads.get_lead(lead_id)["content"] == "hub-written row"
    assert leads.update_lead(lead_id, {"groupName": "G"})["groupName"] == "G"
    leads.delete_lead(lead_id)
    with pytest.raises(ApiError):
        leads.get_lead(lead_id)


def test_date_filters():
    seed_lead(1)   # stored 2026-08-01T09:01
    seed_lead(2)   # stored 2026-08-01T09:02
    tables.upsert(tables.TABLE_LEADS, {
        "PartitionKey": "filtered", "RowKey": "old-lead", "lead_id": "old-lead",
        "content": "old one", "keywords": json.dumps([]), "category": "Regular",
        "stored_at": "2026-05-29T18:23:00Z",   # hub-style 'Z' timestamp
    })
    assert leads.list_leads({})["total"] == 3
    assert leads.list_leads({"from": "2026-08-01"})["total"] == 2
    assert leads.list_leads({"to": "2026-05-29"})["total"] == 1          # bare date is inclusive
    assert leads.list_leads({"from": "2026-05-01", "to": "2026-05-31"})["total"] == 1
    assert leads.list_leads({"from": "2026-08-01T09:01:30+00:00"})["total"] == 1
    # counts respect the date window too
    assert leads.list_leads({"from": "2026-08-01"})["counts"] == {"Subject-To": 2}
    with pytest.raises(ApiError):
        leads.list_leads({"from": "not-a-date"})


def test_url_surfaced_in_detail():
    lead_id = seed_lead(1)
    assert leads.get_lead(lead_id)["url"] == ""   # column absent → empty
    tables.upsert(tables.TABLE_LEADS, {
        "PartitionKey": "filtered", "RowKey": tables.encode_row_key(lead_id),
        "url": "https://www.facebook.com/groups/g/posts/123/",
    })
    assert leads.get_lead(lead_id)["url"] == "https://www.facebook.com/groups/g/posts/123/"


def seed_dated(rk: str, stored_at: str, keep=False, category="Regular"):
    tables.upsert(tables.TABLE_LEADS, {
        "PartitionKey": "filtered", "RowKey": rk, "lead_id": rk,
        "content": "x", "keywords": json.dumps([]), "category": category,
        "stored_at": stored_at, "keep": keep,
    })


def test_purge_requires_to_date_and_defaults_to_dry_run():
    seed_dated("a", "2026-01-05T00:00:00+00:00")
    with pytest.raises(ApiError):
        leads.purge_leads({})
    result = leads.purge_leads({"to": "2026-02-01"})
    assert result["dry_run"] is True and result["would_purge"] == 1
    assert leads.list_leads({})["total"] == 1  # nothing deleted


def test_purge_deletes_in_window_only():
    seed_dated("old", "2026-01-05T00:00:00+00:00")
    seed_dated("new", "2026-07-05T00:00:00+00:00")
    result = leads.purge_leads({"to": "2026-06-30", "dry_run": False})
    assert result["purged"] == 1
    remaining = leads.list_leads({})
    assert remaining["total"] == 1 and remaining["items"][0]["id"] == "new"


def test_purge_skips_kept_and_worked_leads():
    from core import interactions
    seed_dated("kept", "2026-01-05T00:00:00+00:00", keep=True)
    seed_dated("worked", "2026-01-06T00:00:00+00:00")
    seed_dated("stale", "2026-01-07T00:00:00+00:00")
    interactions.create("worked", "alice", {"type": "note", "body": "big multi-unit, still live"})
    result = leads.purge_leads({"to": "2026-02-01", "dry_run": False})
    assert result["purged"] == 1
    assert result["skipped_keep"] == 1 and result["skipped_activity"] == 1
    ids = {ld["id"] for ld in leads.list_leads({})["items"]}
    assert ids == {"kept", "worked"}


def test_purge_include_worked_and_from_bound():
    from core import interactions
    seed_dated("worked", "2026-01-06T00:00:00+00:00")
    seed_dated("early", "2025-12-01T00:00:00+00:00")
    interactions.create("worked", "alice", {"type": "note", "body": "n"})
    result = leads.purge_leads({
        "from": "2026-01-01", "to": "2026-02-01",
        "include_worked": True, "dry_run": False,
    })
    assert result["purged"] == 1  # 'early' outside from-bound, 'worked' included
    assert interactions.list_for_lead("worked") == []  # interactions purged too
    assert {ld["id"] for ld in leads.list_leads({})["items"]} == {"early"}


def test_keep_flag_editable():
    lead_id = seed_lead(1)
    assert leads.update_lead(lead_id, {"keep": True})["keep"] is True
    assert leads.update_lead(lead_id, {"keep": False})["keep"] is False


def test_purge_category_filter():
    seed_dated("sf", "2026-01-05T00:00:00+00:00", category="Seller Finance")
    seed_dated("reg", "2026-01-06T00:00:00+00:00", category="Regular")
    seed_dated("unc", "2026-01-07T00:00:00+00:00", category="")
    result = leads.purge_leads({
        "to": "2026-02-01", "categories": ["Seller Finance", "Unclassified"], "dry_run": False,
    })
    assert result["purged"] == 2
    assert {ld["id"] for ld in leads.list_leads({})["items"]} == {"reg"}
    with pytest.raises(ApiError):
        leads.purge_leads({"to": "2026-02-01", "categories": "Seller Finance"})


def test_purge_by_ttl():
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    seed_dated("old-other", (now - timedelta(days=100)).isoformat(), category="Others")
    seed_dated("new-other", (now - timedelta(days=10)).isoformat(), category="Others")
    seed_dated("old-sf", (now - timedelta(days=100)).isoformat(), category="Seller Finance")
    result = leads.purge_by_ttl({
        "ttl_days": {"Others": 60, "Seller Finance": 365}, "dry_run": False,
    })
    assert result["purged"] == 1  # only the 100-day-old Others lead
    ids = {ld["id"] for ld in leads.list_leads({})["items"]}
    assert ids == {"new-other", "old-sf"}
    with pytest.raises(ApiError):
        leads.purge_by_ttl({"ttl_days": {}})
    with pytest.raises(ApiError):
        leads.purge_by_ttl({"ttl_days": {"Others": "soon"}})
