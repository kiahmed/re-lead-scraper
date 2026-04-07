"""
Mirrors the filterProcessCreativeLeads Logic App filter stage.
Filter rules (cities, HOA patterns) are loaded from values.yaml.

  - City rule:  keywords must contain a configured city (case-insensitive)
  - HOA rule:   reject if HOA is mentioned with a non-zero value

Malformed leads (missing/wrong-typed fields) are skipped with a warning
rather than crashing the whole batch.
"""
import re
from pathlib import Path
import yaml

_CONFIG_PATH = Path(__file__).parent.parent.parent / "values.yaml"


def _load_filter_config() -> tuple[set[str], re.Pattern, re.Pattern]:
    with open(_CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)["filter"]

    cities = {c.lower() for c in cfg["cities"]}
    hoa_zero = re.compile(
        "|".join(cfg["hoa_zero_patterns"]),
        re.IGNORECASE,
    )
    hoa_present = re.compile(r"\bhoa\b", re.IGNORECASE)
    return cities, hoa_zero, hoa_present


_CITY_KEYWORDS, _HOA_ZERO_PATTERNS, _HOA_PRESENT = _load_filter_config()


def _safe_str(value, fallback: str = "") -> str:
    if value is None:
        return fallback
    try:
        return str(value)
    except Exception:
        return fallback


def _safe_keywords(lead: dict) -> list[str]:
    raw = lead.get("keywords")
    if not raw:
        return []
    if not isinstance(raw, list):
        return [_safe_str(raw)]
    return [_safe_str(k) for k in raw if k is not None]


def _passes_city(lead: dict) -> bool:
    keywords = {k.lower() for k in _safe_keywords(lead)}
    return bool(_CITY_KEYWORDS & keywords)


def _passes_hoa(lead: dict) -> bool:
    content = _safe_str(lead.get("content"))
    keywords_str = " ".join(_safe_keywords(lead))
    combined = content + " " + keywords_str

    if not _HOA_PRESENT.search(combined):
        return True  # HOA not mentioned — pass

    return bool(_HOA_ZERO_PATTERNS.search(combined))  # HOA present, must be $0


def filter_leads(leads: list[dict]) -> list[dict]:
    if not isinstance(leads, list):
        print(f"[filter] expected a list of leads, got {type(leads).__name__} — returning empty")
        return []

    passing = []
    for i, lead in enumerate(leads):
        if not isinstance(lead, dict):
            print(f"[filter] lead[{i}] is not a dict ({type(lead).__name__}) — skipping")
            continue
        if not lead.get("id"):
            print(f"[filter] lead[{i}] missing 'id' — skipping")
            continue
        try:
            if _passes_city(lead) and _passes_hoa(lead):
                passing.append(lead)
        except Exception as e:
            print(f"[filter] error evaluating lead[{i}] id={lead.get('id', '?')}: {e} — skipping")

    return passing
