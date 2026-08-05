"""Route table + tiny dispatcher shared by the Azure Functions entry point
and the Flask dev server. Paths are segment patterns; `{name}` captures."""
from urllib.parse import unquote

from . import auth, interactions, leads, meta, users
from .http import ApiError, ApiRequest

# ── handlers ─────────────────────────────────────────────────────────────────
API_VERSION = "2026-08-02.4"


def h_health(req: ApiRequest):
    if req.query.get("debug") == "1":
        # names only + hash prefix of the received token — never values
        from . import security
        token = req.bearer_token()
        return 200, {
            "ok": True,
            "headers": sorted(k.lower() for k in req.headers),
            "token_len": len(token),
            "token_hash_prefix": security.token_hash(token)[:12] if token else "",
        }
    return 200, {"ok": True, "version": API_VERSION}


def h_login(req: ApiRequest):
    return 200, auth.login(req.body.get("username", ""), req.body.get("password", ""))


def h_logout(req: ApiRequest):
    auth.logout(req.bearer_token())
    return 200, {"ok": True}


def h_me(req: ApiRequest):
    return 200, auth.public_user(req.user)


def h_meta(req: ApiRequest):
    return 200, meta.get_meta()


def h_leads_list(req: ApiRequest):
    return 200, leads.list_leads(req.query)


def h_lead_get(req: ApiRequest):
    return 200, leads.get_lead(req.path_params["lead_id"])


def h_leads_purge(req: ApiRequest):
    return 200, leads.purge_leads(req.body)


def h_lead_patch(req: ApiRequest):
    return 200, leads.update_lead(req.path_params["lead_id"], req.body)


def h_lead_delete(req: ApiRequest):
    leads.delete_lead(req.path_params["lead_id"])
    return 200, {"ok": True}


def h_interactions_list(req: ApiRequest):
    return 200, {"items": interactions.list_for_lead(req.path_params["lead_id"])}


def h_interactions_create(req: ApiRequest):
    author = req.user.get("RowKey", "") if req.user else ""
    return 201, interactions.create(req.path_params["lead_id"], author, req.body)


def h_interactions_patch(req: ApiRequest):
    return 200, interactions.patch(req.path_params["lead_id"], req.path_params["iid"], req.body)


def h_interactions_delete(req: ApiRequest):
    interactions.remove(req.path_params["lead_id"], req.path_params["iid"])
    return 200, {"ok": True}


def h_users_list(req: ApiRequest):
    return 200, {"items": users.list_users()}


def h_users_get(req: ApiRequest):
    return 200, users.get_user(req.path_params["username"])


def h_users_patch(req: ApiRequest):
    return 200, users.patch_user(req.path_params["username"], req.body)


# (method, path pattern, handler, auth required)
ROUTES = [
    ("GET",    "health",                                h_health,              False),
    ("POST",   "auth/login",                            h_login,               False),
    ("POST",   "auth/logout",                           h_logout,              True),
    ("GET",    "auth/me",                               h_me,                  True),
    ("GET",    "meta",                                  h_meta,                True),
    ("GET",    "leads",                                 h_leads_list,          True),
    ("POST",   "leads/purge",                           h_leads_purge,         True),
    ("GET",    "leads/{lead_id}",                       h_lead_get,            True),
    ("PATCH",  "leads/{lead_id}",                       h_lead_patch,          True),
    ("DELETE", "leads/{lead_id}",                       h_lead_delete,         True),
    ("GET",    "leads/{lead_id}/interactions",          h_interactions_list,   True),
    ("POST",   "leads/{lead_id}/interactions",          h_interactions_create, True),
    ("PATCH",  "leads/{lead_id}/interactions/{iid}",    h_interactions_patch,  True),
    ("DELETE", "leads/{lead_id}/interactions/{iid}",    h_interactions_delete, True),
    ("GET",    "users",                                 h_users_list,          True),
    ("GET",    "users/{username}",                      h_users_get,           True),
    ("PATCH",  "users/{username}",                      h_users_patch,         True),
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
    """Route `path` (without the /api prefix); returns (status, body)."""
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
        # Safe to apply twice: decoded ids never contain '%'.
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
