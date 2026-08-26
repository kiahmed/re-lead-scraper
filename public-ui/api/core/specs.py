"""Property specs for alert criteria.

The pipeline does not persist structured specs today: the classifier stores
only {"summary": ...} and the spokes read loan_balance / interest_rate / ARV
straight out of the post text when they write the follow-up message. So a
criterion like `interest_rate <= 8` has nothing to compare against unless we
recover the numbers ourselves.

Two sources, in priority order, and every value says which one it came from:

  stored  — the value was in the lead's extracted_info (exact; used the moment
            the pipeline starts persisting specs, no change needed here)
  parsed  — recovered from the post text by the labelled regexes below (good,
            not perfect — the UI shows the marker and the matched snippet)

A field that neither source yields is *unknown*, and every spec criterion
carries its own `unknown: include | exclude` so the user decides what an
unparseable post means for them. We never guess a number to fill a blank.
"""
import re

from . import values

MONEY_FIELDS = {
    "loan_balance", "monthly_payment", "asking_price", "down_payment",
    "seller_carry_amount", "ARV", "arv", "rehab_cost",
}
PERCENT_FIELDS = {"interest_rate"}
TERM_FIELDS = {"term"}
ENUM_FIELDS = {"occupancy_status", "property_condition", "property_type"}

# a currency-ish number, optionally suffixed k/m: $185,000  185k  1.2M  1450
_MONEY = r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?"
_PCT = r"(\d{1,2}(?:\.\d+)?)\s*%"

# label -> number, and number -> label, so both word orders are caught
_FIELD_LABELS: dict[str, str] = {
    "loan_balance": r"loan\s*(?:balance|amount)|mortgage\s*balance|payoff|principal\s*balance|remaining\s*balance|balance\s*(?:of|is|:)|owe[sd]?",
    "monthly_payment": r"monthly\s*payment|payment[s]?\s*(?:of|are|is|:)|piti|p\s*&\s*i|per\s*month|/\s*mo\b|a\s*month",
    "asking_price": r"asking|price|sale\s*price|list(?:ed|ing)?\s*(?:at|price)|selling\s*for|want\s*(?:to\s*get)?",
    "down_payment": r"down\s*payment|down\b|entry\s*fee|cash\s*to\s*(?:close|seller)",
    "seller_carry_amount": r"seller\s*(?:carry|finance|note)|carry\s*(?:back)?|owner\s*carry|second\s*(?:position|lien)",
    "ARV": r"\barv\b|after\s*repair(?:ed)?\s*value|comps?\s*(?:at|around)",
    "rehab_cost": r"rehab|repairs?\s*(?:estimated|cost|around|at)?|reno(?:vation)?\s*(?:cost|budget)?",
}

_ENUM_VALUES: dict[str, dict[str, str]] = {
    "occupancy_status": {
        "vacant": r"\bvacant\b|\bempty\b|no\s*tenant",
        "tenant occupied": r"tenant[- ]?occupied|rented|has\s*(?:a\s*)?tenant|lease\s*in\s*place",
        "owner occupied": r"owner[- ]?occupied|i\s*live\s*(?:there|here|in\s*it)",
    },
    "property_condition": {
        "turnkey": r"turn[- ]?key|move[- ]?in\s*ready|fully\s*(?:renovated|rehabbed)|updated",
        "needs work": r"needs?\s*(?:work|tlc|repairs?|rehab)|fixer|handyman|as[- ]?is|distressed",
        "teardown": r"teardown|gut\s*(?:job|rehab)|burn(?:ed|t)|condemn",
    },
    "property_type": {
        "single family": r"single[- ]?family|\bsfh\b|\bsfr\b|house\b",
        "multi family": r"multi[- ]?family|duplex|triplex|fourplex|quad(?:plex)?|\b\d+\s*unit",
        "land": r"\bland\b|\blot\b|acre[s]?\b|vacant\s*lot",
        "mobile home": r"mobile\s*home|manufactured|trailer|\brv\s*park\b",
        "condo": r"\bcondo|townhome|town\s*house",
        "commercial": r"commercial|retail|warehouse|office\s*(?:building|space)",
    },
}

_WINDOW = 24  # characters allowed between a label and its number


def _money_to_float(number: str, suffix: str) -> float:
    value = float(number.replace(",", ""))
    if suffix and suffix.lower() == "k":
        value *= 1_000
    elif suffix and suffix.lower() == "m":
        value *= 1_000_000
    # bare "185" next to a price label almost always means 185k
    elif not suffix and value < 1000:
        value *= 1_000
    return value


def _find_labelled(text: str, label: str, number: str) -> tuple[re.Match | None, str]:
    """Search label->number then number->label; return the match and a snippet."""
    for pattern in (
        rf"(?:{label})\D{{0,{_WINDOW}}}?{number}",
        rf"{number}\s*(?:{label})",
    ):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m, m.group(0).strip()
    return None, ""


def _parse_money(text: str, field: str) -> tuple[float | None, str]:
    label = _FIELD_LABELS.get(field)
    if not label:
        return None, ""
    m, snippet = _find_labelled(text, label, _MONEY)
    if not m:
        return None, ""
    return _money_to_float(m.group(1), m.group(2) or ""), snippet


def _parse_percent(text: str) -> tuple[float | None, str]:
    # an explicit rate label wins; a bare percentage is the fallback
    m, snippet = _find_labelled(text, r"interest\s*rate|\brate\b|\bapr\b|at\s*a?", _PCT)
    if not m:
        m = re.search(_PCT, text)
        snippet = m.group(0).strip() if m else ""
    if not m:
        return None, ""
    value = float(re.search(_PCT, m.group(0)).group(1))
    return (value, snippet) if 0 < value <= 30 else (None, "")


def _parse_term(text: str) -> tuple[int | None, str]:
    """Normalized to months, because posts mix '30 year' and '360 months'."""
    m = re.search(r"(\d{1,3})\s*(?:-|\s)?\s*(year|yr|y)\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 12, m.group(0).strip()
    m = re.search(r"(\d{1,4})\s*(?:-|\s)?\s*(month|mo)s?\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1)), m.group(0).strip()
    return None, ""


def _parse_enum(text: str, field: str) -> tuple[str | None, str]:
    for label, pattern in _ENUM_VALUES.get(field, {}).items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return label, m.group(0).strip()
    return None, ""


def known_fields() -> list[str]:
    """Every spec field any category can require, plus the ones we can parse
    opportunistically. Order is stable so the UI renders consistently."""
    seen: list[str] = []
    for fields in values.required_fields().values():
        for f in fields:
            if f not in seen:
                seen.append(f)
    for f in ("rehab_cost",):
        if f not in seen:
            seen.append(f)
    return seen


def field_kind(field: str) -> str:
    if field in MONEY_FIELDS:
        return "money"
    if field in PERCENT_FIELDS:
        return "percent"
    if field in TERM_FIELDS:
        return "months"
    if field in ENUM_FIELDS:
        return "enum"
    return "text"


def enum_options(field: str) -> list[str]:
    return list(_ENUM_VALUES.get(field, {}).keys())


def extract(content: str, extracted_info, cities: list[str] | None = None) -> dict[str, dict]:
    """{field: {"value": ..., "source": "stored"|"parsed", "snippet": "..."}}.

    Fields we cannot resolve are simply absent — never present-with-a-guess.
    """
    text = content or ""
    stored = extracted_info if isinstance(extracted_info, dict) else {}
    out: dict[str, dict] = {}

    for field in known_fields():
        if field in stored and stored[field] not in (None, "", []):
            out[field] = {"value": stored[field], "source": "stored", "snippet": ""}
            continue

        kind = field_kind(field)
        value: object | None = None
        snippet = ""
        if kind == "money":
            value, snippet = _parse_money(text, field)
        elif kind == "percent":
            value, snippet = _parse_percent(text)
        elif kind == "months":
            value, snippet = _parse_term(text)
        elif kind == "enum":
            value, snippet = _parse_enum(text, field)
        elif field == "location":
            # the pipeline's own city detection is the honest location signal
            value = ", ".join(cities) if cities else None
            snippet = value or ""

        if value is not None:
            out[field] = {"value": value, "source": "parsed", "snippet": snippet}
    return out
