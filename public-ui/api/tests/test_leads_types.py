"""The pipeline writes is_complete two different ways and one of them lies
when passed through bool()."""
import pytest

from core import criteria, leads


@pytest.mark.parametrize("stored,expected", [
    (True, True), (False, False),
    ("True", True), ("False", False),      # Logic Apps write strings
    ("true", True), ("false", False),
    (None, None), ("", None),
])
def test_as_bool_reads_both_shapes(stored, expected):
    assert leads.as_bool(stored) is expected


def test_bool_of_the_string_false_is_the_trap():
    """This is the whole bug: 79 rows were stored as the string "False"."""
    assert bool("False") is True             # what the old code did
    assert leads.as_bool("False") is False   # what it must do


def test_to_lead_normalizes_before_anything_downstream_sees_it():
    row = {"lead_id": "l1", "content": "post", "is_complete": "False",
           "has_selling_intent": "True", "keywords": "[]"}
    lead = leads.to_lead(row)
    assert lead["is_complete"] is False
    assert lead["has_selling_intent"] is True


@pytest.mark.parametrize("stored", [False, "False"])
def test_a_string_false_lead_is_not_matched_as_complete(stored):
    lead = {"category": "Subject-To", "is_complete": stored, "cities": [],
            "hoa": "none", "content": "", "keywords": [], "authorName": "",
            "groupName": "", "missing_fields": [], "specs": {}}
    assert criteria.match(lead, {"completeness": "complete"}) is False
    assert criteria.match(lead, {"completeness": "incomplete"}) is True


def test_list_filter_agrees_with_the_alert_matcher(make_lead):
    """A filter and an alert must never disagree about the same lead."""
    make_lead("l1", is_complete="False")
    make_lead("l2", is_complete=True)
    complete = leads.list_leads({"is_complete": "true"})
    assert [i["id"] for i in complete["items"]] == ["l2"]
    incomplete = leads.list_leads({"is_complete": "false"})
    assert [i["id"] for i in incomplete["items"]] == ["l1"]
