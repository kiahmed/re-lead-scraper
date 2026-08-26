"""Dispatcher-level tests — the shapes a browser actually sees."""
from core import notes, routes
from core.http import ApiRequest
from core.routes import SERVICE_ACCOUNT


def req(method, headers=None, body=None, query=None):
    return ApiRequest(
        method=method, headers=headers or {}, body=body or {}, query=query or {}
    )


def test_health_and_meta_are_anonymous():
    assert routes.dispatch(req("GET"), "health")[0] == 200
    status, body = routes.dispatch(req("GET"), "meta")
    assert status == 200
    assert "categories" in body and "channels" in body and "spec_fields" in body


def test_meta_advertises_only_configured_channels():
    _, body = routes.dispatch(req("GET"), "meta")
    by_id = {c["id"]: c for c in body["channels"]}
    # conftest switches everything off, so nothing may be offered
    assert not any(c["enabled"] for c in by_id.values())
    # and push must never be described as SMS
    assert "not to a phone number" in by_id["webpush"]["note"]


def test_protected_routes_reject_a_missing_token():
    for method, path in [("GET", "leads"), ("GET", "alerts"), ("GET", "workspace")]:
        status, body = routes.dispatch(req(method), path)
        assert status == 401, path
        assert "error" in body


def test_unknown_path_is_404_and_wrong_method_is_405():
    assert routes.dispatch(req("GET"), "nope")[0] == 404
    assert routes.dispatch(req("POST"), "health")[0] == 405


def test_a_signed_in_user_can_read_leads(make_user, make_lead, token_for):
    make_user()
    make_lead("l1")
    status, body = routes.dispatch(
        req("GET", {"X-Public-Token": token_for("buyer@example.com")}), "leads"
    )
    assert status == 200
    assert body["total"] == 1
    assert body["items"][0]["id"] == "l1"


def test_the_swa_header_is_honoured_as_well_as_bearer(make_user, token_for):
    make_user()
    token = token_for("buyer@example.com")
    for headers in ({"X-Public-Token": token}, {"Authorization": f"Bearer {token}"}):
        assert routes.dispatch(req("GET", headers), "auth/me")[0] == 200


def test_notes_round_trip_through_the_router(make_user, make_lead, token_for):
    make_user()
    make_lead("l1")
    headers = {"X-Public-Token": token_for("buyer@example.com")}

    status, created = routes.dispatch(
        req("POST", headers, {"body": "called the seller"}), "leads/l1/notes"
    )
    assert status == 201

    status, listed = routes.dispatch(req("GET", headers), "leads/l1/notes")
    assert [n["id"] for n in listed["items"]] == [created["id"]]

    status, patched = routes.dispatch(
        req("PATCH", headers, {"body": "left a voicemail"}),
        f"leads/l1/notes/{created['id']}",
    )
    assert patched["body"] == "left a voicemail"
    assert patched["edited"] is True

    assert routes.dispatch(req("DELETE", headers), f"leads/l1/notes/{created['id']}")[0] == 200
    assert routes.dispatch(req("GET", headers), "leads/l1/notes")[1]["items"] == []


def test_a_lead_id_with_percent_escapes_survives_routing(make_user, make_lead, token_for):
    """Base64 lead ids carry '=' padding, which arrives percent-encoded."""
    make_user()
    make_lead("facebook_abc==")
    headers = {"X-Public-Token": token_for("buyer@example.com")}
    status, body = routes.dispatch(req("GET", headers), "leads/facebook_abc%3D%3D")
    assert status == 200
    assert body["id"] == "facebook_abc=="


def test_only_the_service_account_may_run_the_notifier(make_user, token_for):
    make_user()
    status, body = routes.dispatch(
        req("POST", {"X-Public-Token": token_for("buyer@example.com")}, {"dry_run": True}),
        "alerts/run",
    )
    assert status == 403

    from core import tables
    tables.upsert(tables.TABLE_USERS, {
        "PartitionKey": "user", "RowKey": SERVICE_ACCOUNT, "is_active": True,
    })
    status, body = routes.dispatch(
        req("POST", {"X-Public-Token": token_for(SERVICE_ACCOUNT)}, {"dry_run": True}),
        "alerts/run",
    )
    assert status == 200
    assert body["dry_run"] is True


def test_workspace_put_and_read(make_user, make_lead, token_for):
    make_user()
    make_lead("l1")
    headers = {"X-Public-Token": token_for("buyer@example.com")}
    notes.create("buyer@example.com", "l1", {"body": "note"})

    status, entry = routes.dispatch(
        req("PUT", headers, {"pinned": True, "status": "working", "tags": ["hot"]}),
        "workspace/l1",
    )
    assert status == 200 and entry["pinned"] is True and entry["tags"] == ["hot"]

    _, body = routes.dispatch(req("GET", headers), "workspace")
    assert body["items"][0]["status"] == "working"
    assert body["note_counts"]["l1"] == 1


def test_signup_never_returns_a_session():
    status, body = routes.dispatch(
        req("POST", body={"email": "new@example.com", "password": "correct horse battery"}),
        "auth/signup",
    )
    assert status == 201
    assert "token" not in body          # the emailed link is the proof, not this response


def test_signup_does_not_claim_to_have_sent_mail_it_could_not_send():
    """With no mailer configured, telling the user to check their inbox is a
    lie — and they'd wait forever for a link that never comes."""
    _, body = routes.dispatch(
        req("POST", body={"email": "nomailer@example.com", "password": "correct horse battery"}),
        "auth/signup",
    )
    assert body["verification_sent"] is False


def test_signup_reports_a_real_send(monkeypatch):
    monkeypatch.setattr("core.notify.send_email", lambda *a, **k: None)
    _, body = routes.dispatch(
        req("POST", body={"email": "mailed@example.com", "password": "correct horse battery"}),
        "auth/signup",
    )
    assert body["verification_sent"] is True


def test_an_unverified_account_can_still_sign_in_and_browse(make_lead):
    """Verification gates email alerts, not the board — otherwise a missing
    mailer would lock everyone out entirely."""
    routes.dispatch(
        req("POST", body={"email": "unverified@example.com", "password": "correct horse battery"}),
        "auth/signup",
    )
    make_lead("l1")
    status, login = routes.dispatch(
        req("POST", body={"email": "unverified@example.com", "password": "correct horse battery"}),
        "auth/login",
    )
    assert status == 200
    assert login["user"]["email_verified"] is False
    status, listed = routes.dispatch(
        req("GET", {"X-Public-Token": login["token"]}), "leads"
    )
    assert status == 200 and listed["total"] == 1


def test_resend_verification_does_not_reveal_whether_an_account_exists(make_user):
    make_user("real@example.com", verified=False)
    answers = {
        email: routes.dispatch(req("POST", body={"email": email}), "auth/resend-verification")
        for email in ("real@example.com", "ghost@example.com")
    }
    # byte-identical for a real address and a made-up one
    assert answers["real@example.com"] == answers["ghost@example.com"]
    assert answers["ghost@example.com"][0] == 200


def test_oauth_start_for_an_unconfigured_provider_is_refused():
    status, body = routes.dispatch(req("GET"), "auth/oauth/google")
    assert status == 503
    assert "not configured" in body["error"]
    assert routes.dispatch(req("GET"), "auth/oauth/myspace")[0] == 404


def test_internal_errors_never_leak_a_stack_trace(make_user, token_for, monkeypatch):
    make_user()
    monkeypatch.setattr("core.leads.all_leads", lambda: 1 / 0)
    status, body = routes.dispatch(
        req("GET", {"X-Public-Token": token_for("buyer@example.com")}), "leads"
    )
    assert status == 500
    assert body == {"error": "internal error: ZeroDivisionError"}
