"""City and HOA detection for stored leads.

Mirrors the hub Logic App's Filter_Leads rules and reads the SAME source of
truth (values.yaml), so the admin UI labels a lead exactly the way the pipeline
filter would — with plain regex, never a Gemini call.

City:  matched against the scraper's keywords[] (what the hub filters on) and
       the post text, since a post often names the city only in its body.
       No match at all → OTHER_CITY.
HOA:   three honest states rather than a boolean, because "never mentioned" is
       not the same claim as "seller stated $0".
         none — HOA is not mentioned anywhere
         zero — mentioned and explicitly $0 / no HOA / HOA none
         has  — mentioned with something else (i.e. a real fee)
"""
import re
from functools import lru_cache
from pathlib import Path

import yaml

OTHER_CITY = "All Other Cities"

HOA_NOT_MENTIONED = "none"
HOA_ZERO = "zero"
HOA_PRESENT = "has"

_VALUES_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "values.yaml",   # packaged with the API
    Path(__file__).resolve().parents[2] / "values.yaml",   # repo root (local dev)
)


@lru_cache(maxsize=1)
def _config():
    values: dict = {}
    for path in _VALUES_CANDIDATES:
        if path.is_file():
            values = yaml.safe_load(path.read_text()) or {}
            break
    filter_cfg = values.get("filter", {}) or {}

    cities = [str(c) for c in (filter_cfg.get("cities") or [])]
    city_patterns = {
        c.title(): re.compile(rf"\b{re.escape(c)}\b", re.IGNORECASE) for c in cities
    }
    patterns = filter_cfg.get("hoa_zero_patterns") or []
    # r"(?!x)x" never matches — keeps behaviour sane if the list is empty
    hoa_zero = re.compile("|".join(patterns) if patterns else r"(?!x)x", re.IGNORECASE)
    hoa_present = re.compile(r"\bhoa\b", re.IGNORECASE)
    return city_patterns, hoa_zero, hoa_present


def city_options() -> list[str]:
    """Cities the UI can filter by, in config order, plus the catch-all."""
    city_patterns, _, _ = _config()
    return [*city_patterns.keys(), OTHER_CITY]


def _haystack(content: str, keywords) -> str:
    words = " ".join(str(k) for k in keywords) if isinstance(keywords, list) else str(keywords or "")
    return f"{content or ''} {words}"


def detect_cities(content: str, keywords) -> list[str]:
    """Every configured city named in the post or its keywords."""
    city_patterns, _, _ = _config()
    text = _haystack(content, keywords)
    return [name for name, pattern in city_patterns.items() if pattern.search(text)]


def hoa_state(content: str, keywords) -> str:
    text = _haystack(content, keywords)
    _, hoa_zero, hoa_present = _config()
    if not hoa_present.search(text):
        return HOA_NOT_MENTIONED
    return HOA_ZERO if hoa_zero.search(text) else HOA_PRESENT


def matches_city(cities: list[str], wanted: str) -> bool:
    if not wanted:
        return True
    if wanted == OTHER_CITY:
        return not cities
    return wanted in cities
