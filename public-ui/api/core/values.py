"""Single loader for values.yaml — the pipeline's source of truth for
categories, city keywords, HOA patterns, and per-category required fields.
Both the packaged copy (shipped next to the API) and the repo-root copy
(local dev) are supported, in that order."""
from functools import lru_cache
from pathlib import Path

import yaml

_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "values.yaml",   # packaged with the API
    Path(__file__).resolve().parents[3] / "values.yaml",   # repo root (local dev)
)


@lru_cache(maxsize=1)
def load() -> dict:
    for path in _CANDIDATES:
        if path.is_file():
            return yaml.safe_load(path.read_text()) or {}
    return {}


def categories() -> list[str]:
    return list((load().get("classifier", {}).get("categories") or {}).keys())


def required_fields() -> dict[str, list[str]]:
    """Per-category property specs the spokes use to write the follow-up
    message — exactly the fields an alert can filter on."""
    raw = load().get("outreach", {}).get("required_fields") or {}
    return {k: list(v or []) for k, v in raw.items()}
