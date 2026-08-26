"""Environment config for the public API.

Same contract as admin-api/core/config.py — os.environ first, then a .env
file — reimplemented here so the two APIs deploy as independent bundles and
an admin-side refactor can never break the public app.

Search order: $PUBLIC_ENV_FILE, ./.env, repo root .env.
"""
import os
from pathlib import Path

_loaded = False


def _candidate_env_files():
    explicit = os.environ.get("PUBLIC_ENV_FILE")
    if explicit:
        yield Path(explicit)
    yield Path.cwd() / ".env"
    # public-ui/api/core/config.py -> repo root is three levels up
    repo_root = Path(__file__).resolve().parents[3]
    yield repo_root / ".env"
    # inside a git worktree (<main>/.claude/worktrees/<name>) fall back to the
    # main checkout's .env, which deploy.py keeps up to date
    parts = repo_root.parts
    if ".claude" in parts:
        yield Path(*parts[: parts.index(".claude")]) / ".env"


def _load_env_file() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    for path in _candidate_env_files():
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return


def get(key: str, default: str = "") -> str:
    _load_env_file()
    return os.environ.get(key, default)


def flag(key: str, default: bool = False) -> bool:
    raw = get(key, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def storage_connection_string() -> str:
    return get("AZURE_STORAGE_CONNECTION_STRING")


def site_url() -> str:
    """Public origin, used to build OAuth redirect + email verification links."""
    return get("PUBLIC_SITE_URL", "http://localhost:5174").rstrip("/")
