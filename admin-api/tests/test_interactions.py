import pytest

from core import interactions
from core.http import ApiError

LEAD = "facebook_lead+1=="


def test_create_and_list_newest_first():
    a = interactions.create(LEAD, "alice", {"type": "note", "body": "first"})
    b = interactions.create(LEAD, "alice", {"type": "note", "body": "second"})
    items = interactions.list_for_lead(LEAD)
    assert [i["body"] for i in items] == ["second", "first"]  # reverse-tick order
    assert a["id"] != b["id"]
    assert items[0]["author"] == "alice"


def test_type_validation_and_required_body():
    with pytest.raises(ApiError):
        interactions.create(LEAD, "a", {"type": "tweet", "body": "x"})
    with pytest.raises(ApiError):
        interactions.create(LEAD, "a", {"type": "note", "body": "  "})


def test_follow_up_fields():
    item = interactions.create(LEAD, "a", {
        "type": "follow_up", "body": "call Thursday", "follow_up_at": "2026-08-07",
    })
    assert item["follow_up_at"] == "2026-08-07"
    patched = interactions.patch(LEAD, item["id"], {"follow_up_done": True})
    assert patched["follow_up_done"] is True


def test_patch_marks_edited_and_rejects_unknown_fields():
    item = interactions.create(LEAD, "a", {"type": "note", "body": "v1"})
    patched = interactions.patch(LEAD, item["id"], {"body": "v2"})
    assert patched["body"] == "v2"
    assert patched["edited"] is True
    with pytest.raises(ApiError):
        interactions.patch(LEAD, item["id"], {"author": "mallory"})


def test_delete_then_gone():
    item = interactions.create(LEAD, "a", {"type": "note", "body": "bye"})
    interactions.remove(LEAD, item["id"])
    assert interactions.list_for_lead(LEAD) == []
    with pytest.raises(ApiError):
        interactions.patch(LEAD, item["id"], {"body": "zombie"})


def test_leads_partitions_are_isolated():
    interactions.create("lead-A", "a", {"type": "note", "body": "for A"})
    interactions.create("lead-B", "a", {"type": "note", "body": "for B"})
    assert len(interactions.list_for_lead("lead-A")) == 1
