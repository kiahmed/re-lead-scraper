"""The alert criteria matcher — used by BOTH the Settings preview and the
scheduled notifier, so what a user previews is byte-for-byte what fires.

Criteria shape (stored as JSON on the alert row):

    {
      "categories": ["Subject-To", "Hybrid"],   # empty/absent = any
      "cities":     ["Atlanta"],                # empty/absent = any
      "hoa":        ["zero", "none"],           # empty/absent = any
      "completeness": "any" | "complete" | "incomplete",
      "keywords_any":  ["tenant occupied"],     # at least one must appear
      "keywords_none": ["agent"],               # none may appear
      "specs": [
        {"field": "interest_rate", "op": "lte", "value": 8, "unknown": "exclude"}
      ],
      "unknowns_required":  ["location"],       # the spoke still lacks these
      "unknowns_forbidden": ["asking_price"]    # the spoke must already have these
    }

Every clause is AND-ed. An absent clause is "don't care" — never a silent
default that surprises the user at 3am.
"""
from . import leads as _leads
from . import specs, values
from .http import ApiError

COMPLETENESS = ("any", "complete", "incomplete")
OPS = ("eq", "ne", "lt", "lte", "gt", "gte", "between", "contains")
UNKNOWN_MODES = ("include", "exclude")


# ── validation ───────────────────────────────────────────────────────────────
def validate(criteria: dict) -> dict:
    """Reject a bad criteria object at save time rather than at send time —
    a broken alert that only fails inside the cron is invisible to the user."""
    if not isinstance(criteria, dict):
        raise ApiError(400, "criteria must be an object")

    known_categories = set(values.categories())
    for name in ("categories", "cities", "hoa", "keywords_any", "keywords_none",
                 "unknowns_required", "unknowns_forbidden"):
        value = criteria.get(name)
        if value is not None and not isinstance(value, list):
            raise ApiError(400, f"{name} must be a list")

    for cat in criteria.get("categories") or []:
        if known_categories and cat not in known_categories and cat != "Unclassified":
            raise ApiError(400, f"unknown category: {cat}")

    for state in criteria.get("hoa") or []:
        if state not in ("none", "zero", "has"):
            raise ApiError(400, f"hoa must be one of none/zero/has, got {state}")

    completeness = criteria.get("completeness", "any")
    if completeness not in COMPLETENESS:
        raise ApiError(400, f"completeness must be one of {list(COMPLETENESS)}")

    spec_fields = set(specs.known_fields())
    for clause in criteria.get("specs") or []:
        if not isinstance(clause, dict):
            raise ApiError(400, "each spec clause must be an object")
        field = clause.get("field", "")
        if field not in spec_fields:
            raise ApiError(400, f"unknown spec field: {field}")
        op = clause.get("op", "")
        if op not in OPS:
            raise ApiError(400, f"op must be one of {list(OPS)}")
        if op == "between":
            value = clause.get("value")
            if not isinstance(value, list) or len(value) != 2:
                raise ApiError(400, "between takes a [low, high] pair")
        if clause.get("unknown", "exclude") not in UNKNOWN_MODES:
            raise ApiError(400, f"unknown must be one of {list(UNKNOWN_MODES)}")

    for field in (criteria.get("unknowns_required") or []) + (criteria.get("unknowns_forbidden") or []):
        if field not in spec_fields:
            raise ApiError(400, f"unknown spec field: {field}")
    return criteria


# ── matching ─────────────────────────────────────────────────────────────────
def _as_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").replace("%", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _compare(actual, op: str, wanted) -> bool:
    if op == "contains":
        return str(wanted).lower() in str(actual).lower()

    a, b = _as_number(actual), _as_number(wanted if op != "between" else (wanted or [None])[0])
    if a is None:
        # non-numeric field (enum/text): only equality-style ops make sense
        if op == "eq":
            return str(actual).lower() == str(wanted).lower()
        if op == "ne":
            return str(actual).lower() != str(wanted).lower()
        return False

    if op == "between":
        low, high = (_as_number(wanted[0]), _as_number(wanted[1]))
        if low is None or high is None:
            return False
        return low <= a <= high
    if b is None:
        return False
    return {
        "eq": a == b, "ne": a != b,
        "lt": a < b, "lte": a <= b,
        "gt": a > b, "gte": a >= b,
    }[op]


def _missing_for(lead: dict) -> set[str]:
    """What the spoke still doesn't know. Prefer the spoke's own
    missing_fields column; fall back to required_fields minus what we resolved
    so an unprocessed lead still answers the question honestly."""
    reported = lead.get("missing_fields") or []
    if reported:
        return set(reported)
    required = values.required_fields().get(lead.get("category", ""), [])
    resolved = set(lead.get("specs") or {})
    return {f for f in required if f not in resolved}


def match(lead: dict, criteria: dict) -> bool:
    categories = criteria.get("categories") or []
    if categories and (lead.get("category") or "Unclassified") not in categories:
        return False

    cities = criteria.get("cities") or []
    if cities:
        lead_cities = lead.get("cities") or []
        # "All Other Cities" means: matched none of the configured cities
        wants_other = any(c.lower().startswith("all other") for c in cities)
        named = [c for c in cities if not c.lower().startswith("all other")]
        if not ((wants_other and not lead_cities) or (set(named) & set(lead_cities))):
            return False

    hoa = criteria.get("hoa") or []
    if hoa and lead.get("hoa") not in hoa:
        return False

    completeness = criteria.get("completeness", "any")
    if completeness != "any":
        # never bool() the raw value — the Logic Apps store the string "False"
        is_complete = _leads.as_bool(lead.get("is_complete"))
        if is_complete is None:
            return False
        if is_complete != (completeness == "complete"):
            return False

    haystack = " ".join([
        lead.get("content", "") or lead.get("snippet", ""),
        lead.get("authorName", ""), lead.get("groupName", ""),
        " ".join(lead.get("keywords") or []),
    ]).lower()

    any_words = [w.lower() for w in (criteria.get("keywords_any") or []) if w.strip()]
    if any_words and not any(w in haystack for w in any_words):
        return False
    none_words = [w.lower() for w in (criteria.get("keywords_none") or []) if w.strip()]
    if any(w in haystack for w in none_words):
        return False

    lead_specs = lead.get("specs") or {}
    for clause in criteria.get("specs") or []:
        entry = lead_specs.get(clause["field"])
        if entry is None:
            # the spec is unknown for this lead — the user's own call
            if clause.get("unknown", "exclude") == "exclude":
                return False
            continue
        if not _compare(entry.get("value"), clause["op"], clause.get("value")):
            return False

    missing = _missing_for(lead)
    if any(f not in missing for f in (criteria.get("unknowns_required") or [])):
        return False
    return not any(f in missing for f in (criteria.get("unknowns_forbidden") or []))


def filter_leads(leads: list[dict], criteria: dict) -> list[dict]:
    return [ld for ld in leads if match(ld, criteria)]
