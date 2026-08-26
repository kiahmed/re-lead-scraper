"""Social sign-in: Google, Microsoft (OpenID Connect) and Facebook (OAuth2).

Why our own flow rather than Static Web Apps' built-in auth: SWA no longer
ships Google as a preconfigured provider, and registering a custom OIDC
provider requires the SWA **Standard** plan. Doing the authorization-code
hop ourselves keeps the app on the Free tier and reuses the same session
rows as password login.

Endpoints are never hardcoded for the OIDC providers — they come from each
provider's /.well-known/openid-configuration at runtime (cached), so a
provider moving an endpoint can't silently break us. Facebook is not
OIDC-compliant, so its Graph endpoints are pinned to an explicit version.

Only providers with BOTH a client id and secret configured are advertised;
GET /api/meta tells the SPA which buttons to render, so a half-configured
provider can never show a dead button.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

from . import auth, config, security, tables
from .http import ApiError

FACEBOOK_API_VERSION = "v25.0"
STATE_TTL_MINUTES = 10
_STATE_PK = "oauth_state"

PROVIDERS = {
    "google": {
        "label": "Google",
        "kind": "oidc",
        "discovery": "https://accounts.google.com/.well-known/openid-configuration",
        "scope": "openid email profile",
        "client_id_env": "OAUTH_GOOGLE_CLIENT_ID",
        "client_secret_env": "OAUTH_GOOGLE_CLIENT_SECRET",
    },
    "microsoft": {
        "label": "Microsoft",
        "kind": "oidc",
        "discovery": "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
        "scope": "openid email profile",
        "client_id_env": "OAUTH_MICROSOFT_CLIENT_ID",
        "client_secret_env": "OAUTH_MICROSOFT_CLIENT_SECRET",
    },
    "facebook": {
        "label": "Facebook",
        "kind": "facebook",
        "authorize": f"https://www.facebook.com/{FACEBOOK_API_VERSION}/dialog/oauth",
        "token": f"https://graph.facebook.com/{FACEBOOK_API_VERSION}/oauth/access_token",
        "userinfo": f"https://graph.facebook.com/{FACEBOOK_API_VERSION}/me",
        "scope": "email public_profile",
        "client_id_env": "OAUTH_FACEBOOK_CLIENT_ID",
        "client_secret_env": "OAUTH_FACEBOOK_CLIENT_SECRET",
    },
}

_discovery_cache: dict[str, dict] = {}


def _http_json(url: str, data: dict | None = None, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:  # surface the provider's own message
        detail = e.read().decode()[:300]
        raise ApiError(502, f"identity provider rejected the request: {detail}") from None
    except Exception:
        raise ApiError(502, "could not reach the identity provider") from None


def _discovery(provider: str) -> dict:
    cfg = PROVIDERS[provider]
    if provider not in _discovery_cache:
        _discovery_cache[provider] = _http_json(cfg["discovery"])
    return _discovery_cache[provider]


def credentials(provider: str) -> tuple[str, str]:
    cfg = PROVIDERS[provider]
    return config.get(cfg["client_id_env"]), config.get(cfg["client_secret_env"])


def configured(provider: str) -> bool:
    client_id, secret = credentials(provider)
    return bool(client_id and secret)


def available() -> list[dict]:
    """What the SPA should render — label + id for each usable provider."""
    return [
        {"id": name, "label": cfg["label"]}
        for name, cfg in PROVIDERS.items()
        if configured(name)
    ]


def redirect_uri(provider: str) -> str:
    return f"{config.site_url()}/api/auth/oauth/{provider}/callback"


def _store_state(provider: str, next_path: str) -> str:
    """CSRF state, stored server-side with a short TTL. Only the hash is kept,
    so a leaked table can't be replayed into a sign-in."""
    state = security.new_token()
    tables.upsert(tables.TABLE_SESSIONS, {
        "PartitionKey": _STATE_PK,
        "RowKey": security.token_hash(state),
        "provider": provider,
        "next": next_path or "/",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=STATE_TTL_MINUTES)).isoformat(),
    })
    return state


def _consume_state(provider: str, state: str) -> str:
    rk = security.token_hash(state or "")
    row = tables.get_entity(tables.TABLE_SESSIONS, _STATE_PK, rk)
    tables.delete(tables.TABLE_SESSIONS, _STATE_PK, rk)  # single use, always
    if row is None or row.get("provider") != provider:
        raise ApiError(400, "invalid or expired sign-in request — please try again")
    if row.get("expires_at", "") <= datetime.now(UTC).isoformat():
        raise ApiError(400, "sign-in request expired — please try again")
    return row.get("next", "/")


def start(provider: str, next_path: str = "/") -> str:
    """Returns the provider URL to redirect the browser to."""
    if provider not in PROVIDERS:
        raise ApiError(404, "unknown provider")
    if not configured(provider):
        raise ApiError(503, f"{PROVIDERS[provider]['label']} sign-in is not configured")
    cfg = PROVIDERS[provider]
    client_id, _ = credentials(provider)
    endpoint = (
        _discovery(provider)["authorization_endpoint"]
        if cfg["kind"] == "oidc" else cfg["authorize"]
    )
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(provider),
        "response_type": "code",
        "scope": cfg["scope"],
        "state": _store_state(provider, next_path),
    }
    return f"{endpoint}?{urllib.parse.urlencode(params)}"


def _exchange(provider: str, code: str) -> dict:
    cfg = PROVIDERS[provider]
    client_id, client_secret = credentials(provider)
    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri(provider),
        "grant_type": "authorization_code",
    }
    if cfg["kind"] == "oidc":
        return _http_json(
            _discovery(provider)["token_endpoint"], payload,
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
    # Facebook's token endpoint is a GET with query params
    return _http_json(f"{cfg['token']}?{urllib.parse.urlencode(payload)}")


def _identity(provider: str, tokens: dict) -> dict:
    """Ask the provider who this is, using the access token it just issued.

    We call userinfo rather than decoding the id_token ourselves: the token
    came straight from the provider's TLS-protected token endpoint, and
    userinfo requires that same token, so there is no signature to verify and
    no JWT library to keep current.
    """
    access_token = tokens.get("access_token", "")
    if not access_token:
        raise ApiError(502, "identity provider returned no access token")
    cfg = PROVIDERS[provider]
    if cfg["kind"] == "oidc":
        info = _http_json(
            _discovery(provider)["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return {
            "sub": info.get("sub", ""),
            "email": auth.normalize_email(info.get("email", "")),
            "name": info.get("name", ""),
            # Google and Microsoft both report this; absence means "not asserted"
            "email_verified": bool(info.get("email_verified", False)),
        }
    query = urllib.parse.urlencode({"fields": "id,name,email", "access_token": access_token})
    info = _http_json(f"{cfg['userinfo']}?{query}")
    return {
        "sub": info.get("id", ""),
        "email": auth.normalize_email(info.get("email", "")),
        "name": info.get("name", ""),
        # Facebook only returns an email at all if it is confirmed on the account
        "email_verified": bool(info.get("email")),
    }


def _link_or_create(provider: str, identity: dict) -> dict:
    email = identity["email"]
    if not email:
        raise ApiError(
            400,
            f"{PROVIDERS[provider]['label']} did not share an email address — "
            "grant the email permission, or sign up with an email and password",
        )

    now = datetime.now(UTC).isoformat()
    row = auth.get_user_row(email)
    link = {"provider": provider, "sub": identity["sub"]}

    if row is None:
        row = {
            "PartitionKey": auth.USER_PK, "RowKey": email,
            "password_hash": "",
            "display_name": identity.get("name") or email.split("@")[0],
            # trust the provider's own verification, and only that
            "email_verified": bool(identity["email_verified"]),
            "providers": json.dumps([link]),
            "phone": "", "phone_verified": False,
            "tz": "America/New_York",
            "is_active": True, "failed_attempts": 0, "locked_until": "",
            "created_at": now, "updated_at": now, "last_login_at": now,
        }
        tables.upsert(tables.TABLE_USERS, row)
        return row

    if not bool(row.get("is_active", True)):
        raise ApiError(401, "account disabled")

    # Linking a social identity onto an existing password account is only safe
    # when the provider asserts the address is verified — otherwise anyone who
    # can type an email at a sloppy provider could seize the account.
    if not identity["email_verified"]:
        raise ApiError(
            401,
            f"{PROVIDERS[provider]['label']} has not verified that address — "
            "sign in with your password instead",
        )

    links = json.loads(row.get("providers", "[]") or "[]")
    if not any(entry.get("provider") == provider for entry in links):
        links.append(link)
    update = {
        "PartitionKey": auth.USER_PK, "RowKey": email,
        "providers": json.dumps(links),
        "email_verified": True,
        "failed_attempts": 0, "locked_until": "",
        "last_login_at": now, "updated_at": now,
    }
    tables.upsert(tables.TABLE_USERS, update)
    return {**row, **update}


def callback(provider: str, code: str, state: str) -> tuple[str, str, dict]:
    """(next_path, session_token, public_user) after a successful hop."""
    if provider not in PROVIDERS:
        raise ApiError(404, "unknown provider")
    next_path = _consume_state(provider, state)
    if not code:
        raise ApiError(400, "sign-in was cancelled")
    row = _link_or_create(provider, _identity(provider, _exchange(provider, code)))
    token = auth._issue_session(row["RowKey"])
    return next_path, token, auth.public_user(row)


def purge_expired_states() -> int:
    now = datetime.now(UTC).isoformat()
    purged = 0
    for row in tables.query(tables.TABLE_SESSIONS, f"PartitionKey eq '{_STATE_PK}'"):
        if row.get("expires_at", "") <= now:
            tables.delete(tables.TABLE_SESSIONS, _STATE_PK, row["RowKey"])
            purged += 1
    return purged
