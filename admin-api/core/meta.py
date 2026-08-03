"""Meta endpoint — categories and required fields come from values.yaml
(the single source of truth) so the UI never hardcodes them."""
from functools import lru_cache
from pathlib import Path

import yaml

from . import tables

_VALUES_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "values.yaml",   # packaged with the API
    Path(__file__).resolve().parents[2] / "values.yaml",   # repo root (local dev)
)


@lru_cache(maxsize=1)
def _values() -> dict:
    for path in _VALUES_CANDIDATES:
        if path.is_file():
            return yaml.safe_load(path.read_text()) or {}
    return {}


def get_meta() -> dict:
    values = _values()
    categories = list((values.get("classifier", {}).get("categories") or {}).keys())
    required_fields = values.get("outreach", {}).get("required_fields") or {}
    version = tables.get_entity(tables.TABLE_VERSIONS, "pipeline", "config") or {}
    return {
        "categories": categories,
        "required_fields": required_fields,
        "pipeline": {
            "status": version.get("status", "unknown"),
            "deployed_at": version.get("deployed_at", ""),
            "synced_at": version.get("synced_at", ""),
        },
    }
