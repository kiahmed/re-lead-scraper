"""Environment config for the admin API.

Reads os.environ first; falls back to a .env file so local runs work the
same way as the pipeline code (deploy.py writes connection strings there).
Search order: $ADMIN_ENV_FILE, ./.env, repo root .env (two levels up from
this file's package).
"""
import os
from pathlib import Path

_loaded = False


def _candidate_env_files():
    explicit = os.environ.get("ADMIN_ENV_FILE")
    if explicit:
        yield Path(explicit)
    yield Path.cwd() / ".env"
    repo_root = Path(__file__).resolve().parents[2]
    yield repo_root / ".env"
    # inside a git worktree (<main>/.claude/worktrees/<name>) fall back to
    # the main checkout's .env, which deploy.py keeps up to date
    parts = repo_root.parts
    if ".claude" in parts:
        main_root = Path(*parts[: parts.index(".claude")])
        yield main_root / ".env"


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
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
        return


def get(key: str, default: str = "") -> str:
    _load_env_file()
    return os.environ.get(key, default)


def storage_connection_string() -> str:
    return get("AZURE_STORAGE_CONNECTION_STRING")
