"""Route table + dispatcher shared by the Azure Functions entry point and the
Flask dev server.

Read the table before adding anything: there is deliberately NO route that
writes to a lead. `PATCH /leads/{id}`, `DELETE /leads/{id}` and
`POST /leads/purge` do not exist here, so no request can reach pipeline data.
A public user's writes land only in the pub* tables, always partitioned by
the id on their session.
"""
from urllib.parse import unquote

from . import alerts, auth, digest, leads, meta, notes, notify, oauth, saved
from .http import ApiError, ApiRequest

API_VERSION = "2026-08-24.1"
SERVICE_ACCOUNT = "service@flynest.internal"


def _uid(req: ApiRequest) -> str:
    return auth.user_id(req.user)


# ── public ───────────────────────────────────────────────────────────────────
def h_health(req: ApiRequest):
    return 200, {"ok": True, "version": API_VERSION}


def h_meta(req: ApiRequest):
    return 200, meta.get_meta()


def h_signup(req: ApiRequest):
    result = auth.signup(
        req.body.get("email", ""), req.body.get("password", ""),
        req.body.get("display_name", ""),
    )
    email = result["user"]["email"]
    sent = _send_verification(email, result["verify_token"])
    # No session here — the emailed link is what proves the address. The
    # account still works without it: sign in with the password and browse.
    # Only email alerts stay locked until the address is confirmed.
    return 201, {"ok": True, "email": email, "verification_sent": sent}


def h_login(req: ApiRequest):
    return 200, auth.login(req.body.get("email", ""), req.body.get("password", ""))


def h_logout(req: ApiRequest):
    auth.logout(req.bearer_token())
    return 200, {"ok": True}


def h_me(req: ApiRequest):
    return 200, auth.public_user(req.user)


def h_verify(req: ApiRequest):
    return 200, auth.verify_email(req.body.get("token", "") or req.query.get("token", ""))


def h_resend_verification(req: ApiRequest):
    email = auth.normalize_email(req.body.get("email", ""))
    row = auth.get_user_row(email)
    # Always the same answer, so this can't be used to test which addresses exist.
    if row is not None and not bool(row.get("email_verified", False)):
        _send_verification(email, auth.new_verification_token(email))
    return 200, {"ok": True, "email_configured": notify.email_enabled()}


def _send_verification(email: str, token: str) -> bool:
    """True if a link actually went out. Signup must not fail because the
    mailer is down or unconfigured — but it must not claim to have sent
    something it didn't, either."""
    from . import config
    link = f"{config.site_url()}/verify?token={token}"
    try:
        notify.send_email(
            email, "Confirm your email",
            "Welcome to FlyNest Leads.\n\n"
            f"Confirm your address to start saving notes and alerts:\n{link}\n\n"
            f"The link is good for {auth.VERIFY_TTL_HOURS} hours. "
            "If you didn't sign up, ignore this email.",
        )
    except notify.NotifyError:
        return False
    return True


def h_oauth_start(req: ApiRequest):
    req.redirect = oauth.start(req.path_params["provider"], req.query.get("next", "/"))
    return 302, {}


def h_oauth_callback(req: ApiRequest):
    from . import config
    provider = req.path_params["provider"]
    next_path, token, _user = oauth.callback(
        provider, req.query.get("code", ""), req.query.get("state", ""),
    )
    # Hand the token to the SPA through the URL fragment: fragments are never
    # sent to a server or written to proxy logs, and the SPA strips it on load.
    req.redirect = f"{config.site_url()}/auth/callback#token={token}&next={next_path}"
    return 302, {}


# ── leads (read only) ────────────────────────────────────────────────────────
def h_leads_list(req: ApiRequest):
    return 200, leads.list_leads(req.query)


def h_lead_get(req: ApiRequest):
    return 200, leads.get_lead(req.path_params["lead_id"])


# ── notes ────────────────────────────────────────────────────────────────────
def h_notes_list(req: ApiRequest):
    return 200, {"items": notes.list_for_lead(_uid(req), req.path_params["lead_id"])}


def h_notes_create(req: ApiRequest):
    return 201, notes.create(_uid(req), req.path_params["lead_id"], req.body)


def h_notes_patch(req: ApiRequest):
    return 200, notes.update(_uid(req), req.path_params["nid"], req.body)


def h_notes_delete(req: ApiRequest):
    notes.remove(_uid(req), req.path_params["nid"])
    return 200, {"ok": True}


# ── workspace ────────────────────────────────────────────────────────────────
def h_workspace(req: ApiRequest):
    uid = _uid(req)
    return 200, {
        "items": saved.list_for_user(uid),
        "note_counts": notes.counts_by_lead(uid),
        "notes": notes.list_all(uid),
    }


def h_workspace_put(req: ApiRequest):
    return 200, saved.put(_uid(req), req.path_params["lead_id"], req.body)


def h_workspace_delete(req: ApiRequest):
    saved.remove(_uid(req), req.path_params["lead_id"])
    return 200, {"ok": True}


# ── profile ──────────────────────────────────────────────────────────────────
def h_profile_patch(req: ApiRequest):
    return 200, auth.update_profile(_uid(req), req.body)


def h_password_put(req: ApiRequest):
    auth.set_password(_uid(req), req.body.get("current", ""), req.body.get("new", ""))
    return 200, {"ok": True}


# ── alerts ───────────────────────────────────────────────────────────────────
def h_alerts_list(req: ApiRequest):
    return 200, {"items": alerts.list_for_user(_uid(req))}


def h_alerts_create(req: ApiRequest):
    return 201, alerts.create(_uid(req), req.user or {}, req.body)


def h_alerts_patch(req: ApiRequest):
    return 200, alerts.update(_uid(req), req.path_params["aid"], req.user or {}, req.body)


def h_alerts_delete(req: ApiRequest):
    alerts.remove(_uid(req), req.path_params["aid"])
    return 200, {"ok": True}


def h_alerts_preview(req: ApiRequest):
    return 200, alerts.preview(req.body)


def h_alerts_test(req: ApiRequest):
    uid = _uid(req)
    alert = alerts.get(uid, req.path_params["aid"])
    return 200, {"outcomes": digest.send_test(uid, req.user or {}, alert)}


def h_alerts_run(req: ApiRequest):
    """Cron entry point. Only the service account may call it — a normal
    user's token gets a 403 rather than the ability to fire everyone's alerts."""
    if (req.user or {}).get("RowKey", "") != SERVICE_ACCOUNT:
        raise ApiError(403, "not permitted")
    return 200, digest.run(
        limit_alerts=int(req.body.get("limit", 0) or 0),
        dry_run=bool(req.body.get("dry_run", False)),
    )


# ── push subscriptions ───────────────────────────────────────────────────────
def h_push_list(req: ApiRequest):
    from . import config
    return 200, {
        "items": alerts.list_push(_uid(req)),
        "public_key": config.get("VAPID_PUBLIC_KEY"),
    }


def h_push_create(req: ApiRequest):
    return 201, alerts.add_push(_uid(req), req.body.get("subscription") or req.body)


def h_push_delete(req: ApiRequest):
    alerts.remove_push(_uid(req), req.path_params["pid"])
    return 200, {"ok": True}


# (method, path pattern, handler, auth required)
ROUTES = [
    ("GET",    "health",                          h_health,              False),
    ("GET",    "meta",                            h_meta,                False),

    ("POST",   "auth/signup",                     h_signup,              False),
    ("POST",   "auth/login",                      h_login,               False),
    ("POST",   "auth/logout",                     h_logout,              True),
    ("GET",    "auth/me",                         h_me,                  True),
    ("POST",   "auth/verify",                     h_verify,              False),
    ("POST",   "auth/resend-verification",        h_resend_verification, False),
    ("GET",    "auth/oauth/{provider}",           h_oauth_start,         False),
    ("GET",    "auth/oauth/{provider}/callback",  h_oauth_callback,      False),
    ("PATCH",  "auth/profile",                    h_profile_patch,       True),
    ("PUT",    "auth/password",                   h_password_put,        True),

    ("GET",    "leads",                           h_leads_list,          True),
    ("GET",    "leads/{lead_id}",                 h_lead_get,            True),
    ("GET",    "leads/{lead_id}/notes",           h_notes_list,          True),
    ("POST",   "leads/{lead_id}/notes",           h_notes_create,        True),
    ("PATCH",  "leads/{lead_id}/notes/{nid}",     h_notes_patch,         True),
    ("DELETE", "leads/{lead_id}/notes/{nid}",     h_notes_delete,        True),

    ("GET",    "workspace",                       h_workspace,           True),
    ("PUT",    "workspace/{lead_id}",             h_workspace_put,       True),
    ("DELETE", "workspace/{lead_id}",             h_workspace_delete,    True),

    ("GET",    "alerts",                          h_alerts_list,         True),
    ("POST",   "alerts",                          h_alerts_create,       True),
    ("POST",   "alerts/preview",                  h_alerts_preview,      True),
    ("POST",   "alerts/run",                      h_alerts_run,          True),
    ("PATCH",  "alerts/{aid}",                    h_alerts_patch,        True),
    ("DELETE", "alerts/{aid}",                    h_alerts_delete,       True),
    ("POST",   "alerts/{aid}/test",               h_alerts_test,         True),

    ("GET",    "push",                            h_push_list,           True),
    ("POST",   "push",                            h_push_create,         True),
    ("DELETE", "push/{pid}",                      h_push_delete,         True),
]


def _match(pattern: str, path: str) -> dict | None:
    p_segs = pattern.split("/")
    segs = [s for s in path.strip("/").split("/") if s != ""]
    if len(p_segs) != len(segs):
        return None
    params = {}
    for p, s in zip(p_segs, segs, strict=True):
        if p.startswith("{") and p.endswith("}"):
            params[p[1:-1]] = s
        elif p != s:
            return None
    return params


def dispatch(req: ApiRequest, path: str) -> tuple[int, dict]:
    """Route `path` (without the /api prefix); returns (status, body).
    A 302 carries its target on req.redirect for the adapter to honour."""
    matched_path = False
    for method, pattern, handler, needs_auth in ROUTES:
        params = _match(pattern, path)
        if params is None:
            continue
        matched_path = True
        if method != req.method:
            continue
        # Flask decodes %-escapes in path segments, Azure Functions does not —
        # normalize so lead ids with base64 padding (%3D etc.) work on both.
        req.path_params = {k: unquote(v) for k, v in params.items()}
        try:
            if needs_auth:
                req.user = auth.validate_token(req.bearer_token())
            return handler(req)
        except ApiError as e:
            return e.status, {"error": e.message}
        except Exception as e:  # never leak stack traces to the client
            return 500, {"error": f"internal error: {type(e).__name__}"}
    if matched_path:
        return 405, {"error": "method not allowed"}
    return 404, {"error": "not found"}
