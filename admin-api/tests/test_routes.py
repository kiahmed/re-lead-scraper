from core import users
from core.http import ApiRequest
from core.routes import dispatch


def _req(method="GET", body=None, token="", query=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return ApiRequest(method=method, body=body or {}, headers=headers, query=query or {})


def _login() -> str:
    users.create_user("alice", "correct-horse")
    status, body = dispatch(_req("POST", {"username": "alice", "password": "correct-horse"}), "auth/login")
    assert status == 200
    return body["token"]


def test_health_is_anonymous():
    status, body = dispatch(_req(), "health")
    assert (status, body["ok"]) == (200, True)


def test_protected_routes_require_token():
    for path in ("leads", "users", "meta", "auth/me"):
        status, _body = dispatch(_req(), path)
        assert status == 401, path


def test_login_then_me_then_logout():
    token = _login()
    status, body = dispatch(_req(token=token), "auth/me")
    assert (status, body["username"]) == (200, "alice")
    status, _ = dispatch(_req("POST", token=token), "auth/logout")
    assert status == 200
    status, _ = dispatch(_req(token=token), "auth/me")
    assert status == 401


def test_unknown_path_404_wrong_method_405():
    token = _login()
    assert dispatch(_req(token=token), "nope/nope")[0] == 404
    assert dispatch(_req("DELETE", token=token), "leads")[0] == 405


def test_interaction_author_comes_from_session_not_payload():
    token = _login()
    status, body = dispatch(
        _req("POST", {"type": "note", "body": "hi", "author": "mallory"}, token=token),
        "leads/some-lead/interactions",
    )
    assert status == 201
    assert body["author"] == "alice"


def test_internal_errors_do_not_leak_details(monkeypatch):
    token = _login()
    from core import routes

    def boom(req):
        raise RuntimeError("secret connection string xyz")

    monkeypatch.setitem(
        routes.__dict__, "ROUTES",
        [("GET", "boom", boom, True)] + routes.ROUTES,
    )
    status, body = dispatch(_req(token=token), "boom")
    assert status == 500
    assert "xyz" not in str(body)


def test_encoded_path_params_are_normalized():
    """Azure Functions passes %-encoded route segments through undecoded;
    the dispatcher must handle both encoded and decoded forms."""
    import json as _json

    from core import tables
    token = _login()
    lead_id = "facebook_lead+1=="
    tables.upsert(tables.TABLE_LEADS, {
        "PartitionKey": "filtered",
        "RowKey": tables.encode_row_key(lead_id),
        "lead_id": lead_id,
        "content": "padded id lead",
        "stored_at": "2026-08-01T09:00:00+00:00",
        "keywords": _json.dumps([]),
    })
    encoded = "facebook_lead%2B1%3D%3D"   # what Azure delivers
    decoded = lead_id                      # what Flask delivers
    for variant in (encoded, decoded):
        status, body = dispatch(_req(token=token), f"leads/{variant}")
        assert status == 200, variant
        assert body["content"] == "padded id lead"
