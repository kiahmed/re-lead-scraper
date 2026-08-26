"""The pipeline writes booleans two ways and one of them lies through bool().

Measured on the live table: is_complete was 267 real bools and 127 strings;
has_selling_intent was strings on every single row.
"""
import pytest

from core import leads


@pytest.mark.parametrize("stored,expected", [
    (True, True), (False, False),
    ("True", True), ("False", False),      # what the Logic Apps write
    ("true", True), ("false", False),
    (None, None), ("", None),
])
def test_as_bool_reads_both_shapes(stored, expected):
    assert leads.as_bool(stored) is expected


def test_the_trap():
    assert bool("False") is True             # what the old code did
    assert leads.as_bool("False") is False   # what it must do


def test_to_lead_normalizes_at_the_parse_boundary():
    lead = leads._to_lead({
        "lead_id": "l1", "content": "post", "keywords": "[]",
        "is_complete": "False", "has_selling_intent": "False",
    })
    # the UI renders these with plain truthiness, so a string here shows a
    # green "Complete" tick on an incomplete lead
    assert lead["is_complete"] is False
    assert lead["has_selling_intent"] is False


def test_completeness_filter_excludes_a_string_false_lead(fake_tables):
    import json
    table = fake_tables.get("leads")
    for rk, complete in (("a", "False"), ("b", "True")):
        table.upsert_entity({
            "PartitionKey": "filtered", "RowKey": rk, "lead_id": rk,
            "content": "post", "keywords": json.dumps([]),
            "is_complete": complete, "stored_at": f"2026-08-2{rk == 'b'}T00:00:00+00:00",
        })
    assert [i["id"] for i in leads.list_leads({"is_complete": "true"})["items"]] == ["b"]
    assert [i["id"] for i in leads.list_leads({"is_complete": "false"})["items"]] == ["a"]
