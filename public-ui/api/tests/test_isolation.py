"""The two safety properties this whole app rests on:

  1. the public API cannot write to pipeline data
  2. one user cannot reach another user's data

Both are meant to hold structurally — not because a handler remembered to
check. These tests assert the structure, not the politeness.
"""
import pytest

from core import notes, routes, saved, tables
from core.http import ApiError


# ── 1. pipeline data is unreachable for writes ───────────────────────────────
def test_no_route_writes_to_a_lead():
    write_methods = {"POST", "PATCH", "PUT", "DELETE"}
    lead_writes = [
        (m, p) for m, p, _, _ in routes.ROUTES
        if m in write_methods and p.startswith("leads")
        and not p.endswith("notes") and "/notes/" not in p
    ]
    assert lead_writes == [], f"a lead write route exists: {lead_writes}"


def test_no_purge_or_user_admin_routes_exist():
    paths = [p for _, p, _, _ in routes.ROUTES]
    assert not any("purge" in p for p in paths)
    assert not any(p == "users" or p.startswith("users/") for p in paths)


@pytest.mark.parametrize("table", ["leads", "appversions"])
def test_the_table_layer_refuses_pipeline_writes(table):
    with pytest.raises(RuntimeError, match="read-only"):
        tables.upsert(table, {"PartitionKey": "filtered", "RowKey": "x"})
    with pytest.raises(RuntimeError, match="read-only"):
        tables.delete(table, "filtered", "x")


def test_every_authenticated_route_requires_auth():
    """Anything touching user data must be behind auth; the only anonymous
    routes are health, meta and the sign-in flow."""
    anonymous = {p for m, p, _, needs in routes.ROUTES if not needs}
    assert anonymous == {
        "health", "meta", "auth/signup", "auth/login", "auth/verify",
        "auth/resend-verification", "auth/oauth/{provider}",
        "auth/oauth/{provider}/callback",
    }


# ── 2. users cannot reach each other ─────────────────────────────────────────
def test_a_note_is_only_visible_to_its_author():
    notes.create("alice@example.com", "lead-1", {"body": "my private read"})
    assert len(notes.list_for_lead("alice@example.com", "lead-1")) == 1
    assert notes.list_for_lead("mallory@example.com", "lead-1") == []


def test_a_user_cannot_edit_or_delete_someone_elses_note():
    created = notes.create("alice@example.com", "lead-1", {"body": "mine"})
    with pytest.raises(ApiError) as e:
        notes.update("mallory@example.com", created["id"], {"body": "tampered"})
    assert e.value.status == 404
    with pytest.raises(ApiError):
        notes.remove("mallory@example.com", created["id"])
    # untouched
    assert notes.list_for_lead("alice@example.com", "lead-1")[0]["body"] == "mine"


def test_workspace_entries_are_per_user():
    saved.put("alice@example.com", "lead-1", {"pinned": True, "status": "working"})
    assert len(saved.list_for_user("alice@example.com")) == 1
    assert saved.list_for_user("mallory@example.com") == []
    assert saved.get("mallory@example.com", "lead-1") is None


def test_partition_key_comes_from_the_session_not_the_request():
    """notes.create takes uid as its own argument — there is no field in the
    payload that could redirect the write into another partition."""
    created = notes.create("alice@example.com", "lead-1", {
        "body": "hi", "PartitionKey": "mallory@example.com", "uid": "mallory@example.com",
    })
    rows = tables.query(tables.TABLE_NOTES, "PartitionKey eq 'alice@example.com'")
    assert [r["RowKey"] for r in rows] == [created["id"]]
    assert tables.query(tables.TABLE_NOTES, "PartitionKey eq 'mallory@example.com'") == []
