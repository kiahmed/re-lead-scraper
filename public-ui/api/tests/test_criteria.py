"""criteria.match() is used by BOTH the Settings preview and the notifier,
so every case here is simultaneously a test of what a user sees and of what
gets sent at 3am."""
import pytest

from core import criteria
from core.http import ApiError


def lead(**over):
    base = {
        "category": "Subject-To", "cities": ["Atlanta"], "hoa": "zero",
        "is_complete": True, "content": "tenant occupied, no hoa", "keywords": [],
        "authorName": "", "groupName": "", "missing_fields": [],
        "specs": {"interest_rate": {"value": 4.25, "source": "parsed", "snippet": ""},
                  "loan_balance": {"value": 185000, "source": "parsed", "snippet": ""}},
    }
    return {**base, **over}


def test_empty_criteria_matches_everything():
    assert criteria.match(lead(), {})


@pytest.mark.parametrize("rules,expected", [
    ({"categories": ["Subject-To"]}, True),
    ({"categories": ["Fix & Flip"]}, False),
    ({"cities": ["Atlanta"]}, True),
    ({"cities": ["Savannah"]}, False),
    ({"hoa": ["zero", "none"]}, True),
    ({"hoa": ["has"]}, False),
    ({"completeness": "complete"}, True),
    ({"completeness": "incomplete"}, False),
    ({"keywords_any": ["tenant"]}, True),
    ({"keywords_any": ["vacant"]}, False),
    ({"keywords_none": ["tenant"]}, False),
])
def test_each_dimension(rules, expected):
    assert criteria.match(lead(), rules) is expected


def test_clauses_are_anded():
    assert not criteria.match(lead(), {"categories": ["Subject-To"], "cities": ["Savannah"]})


def test_all_other_cities_means_matched_none_of_the_configured_ones():
    assert criteria.match(lead(cities=[]), {"cities": ["All Other Cities"]})
    assert not criteria.match(lead(), {"cities": ["All Other Cities"]})


@pytest.mark.parametrize("op,value,expected", [
    ("lte", 8, True), ("lte", 3, False),
    ("gte", 4, True), ("gt", 4.25, False),
    ("between", [3, 5], True), ("between", [5, 9], False),
])
def test_numeric_spec_ops(op, value, expected):
    rules = {"specs": [{"field": "interest_rate", "op": op, "value": value}]}
    assert criteria.match(lead(), rules) is expected


def test_unknown_spec_is_the_users_call_not_ours():
    """The whole point of the unknown flag: an unparseable post must not
    silently pass or silently fail."""
    rules = {"specs": [{"field": "ARV", "op": "lte", "value": 300000, "unknown": "exclude"}]}
    assert not criteria.match(lead(), rules)
    rules["specs"][0]["unknown"] = "include"
    assert criteria.match(lead(), rules)


def test_unknowns_use_the_spokes_own_missing_fields():
    ld = lead(missing_fields=["location", "occupancy_status"])
    assert criteria.match(ld, {"unknowns_required": ["location"]})
    assert not criteria.match(ld, {"unknowns_required": ["asking_price"]})
    assert criteria.match(ld, {"unknowns_forbidden": ["asking_price"]})
    assert not criteria.match(ld, {"unknowns_forbidden": ["location"]})


def test_missing_fields_falls_back_to_required_minus_resolved():
    """A lead the spokes never processed still answers 'what's unknown here'
    honestly, rather than claiming everything is known."""
    ld = lead(missing_fields=[])
    assert criteria.match(ld, {"unknowns_required": ["monthly_payment"]})


@pytest.mark.parametrize("bad", [
    {"categories": "Subject-To"},
    {"hoa": ["maybe"]},
    {"completeness": "sort of"},
    {"specs": [{"field": "not_a_field", "op": "lte", "value": 1}]},
    {"specs": [{"field": "ARV", "op": "approximately", "value": 1}]},
    {"specs": [{"field": "ARV", "op": "between", "value": 5}]},
    {"unknowns_required": ["nope"]},
])
def test_bad_criteria_is_rejected_at_save_time(bad):
    with pytest.raises(ApiError):
        criteria.validate(bad)
