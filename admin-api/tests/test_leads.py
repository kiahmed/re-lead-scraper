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
