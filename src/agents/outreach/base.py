"""
Base class for all category outreach agents.

Each subclass declares one class attribute:
    CATEGORY = "Subject-To"   # must match a key in values.yaml outreach.personas

The base class owns:
  - YAML config loading (required_fields + system_prompt for the category)
  - User content formatting
  - Gemini tool definition (_build_tool)
  - HTTP call with retry (same logic as classifier_agent)
  - Response parsing

Subclasses contain only:
    class SubjectToAgent(BaseOutreachAgent):
        CATEGORY = "Subject-To"
"""
import json
import time
import yaml
import requests
from pathlib import Path
from requests.exceptions import Timeout, ConnectionError, ChunkedEncodingError

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "values.yaml"

# ── Retry config (mirrors classifier_agent) ───────────────────────────────────
_RETRY_ON_STATUS: dict[int, int] = {
    408: 10,
    429: 60,
    500: 10,
    502: 10,
    503: 15,
    504: 10,
}
_NO_RETRY_STATUS = {400, 401, 403, 404}
_RETRYABLE_EXCEPTIONS = (Timeout, ConnectionError, ChunkedEncodingError)
MAX_RETRIES = 3


def _load_outreach_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)["outreach"]


def _request_with_retry(
    url: str, payload: dict, headers: dict, label: str, timeout: int = 60
) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        resp: requests.Response | None = None
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except _RETRYABLE_EXCEPTIONS as e:
            last_exc = e
            wait = 5 * (2 ** attempt)
            if attempt < MAX_RETRIES:
                print(f"[{label}] {type(e).__name__} — retrying in {wait}s "
                      f"(attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            raise

        if resp.status_code in _NO_RETRY_STATUS:
            resp.raise_for_status()

        if resp.status_code in _RETRY_ON_STATUS:
            wait = _RETRY_ON_STATUS[resp.status_code] * (2 ** attempt)
            if attempt < MAX_RETRIES:
                print(f"[{label}] HTTP {resp.status_code} — retrying in {wait}s "
                      f"(attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            resp.raise_for_status()

        resp.raise_for_status()
        return resp

    if last_exc:
        raise last_exc
    raise RuntimeError(f"[{label}] Request failed after all retries")


class BaseOutreachAgent:
    CATEGORY: str = ""  # set by subclass

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash", thinking_level: str = ""):
        self.api_key = api_key
        self.model = model
        self.thinking_level = thinking_level
        cfg = _load_outreach_config()
        self.required_fields: list[str] = cfg["required_fields"].get(self.CATEGORY, [])
        self.system_prompt: str = cfg["personas"][self.CATEGORY]["system_prompt"].strip()
        self._label = f"outreach:{self.CATEGORY}"

    # ── responseSchema definition ─────────────────────────────────────────────
    def _build_schema(self) -> dict:
        from src.sync.workflow_builder import _build_outreach_schema
        return _build_outreach_schema(self.CATEGORY, self.required_fields)

    # ── User content builder ──────────────────────────────────────────────────
    def _build_user_content(self, classified: dict, lead: dict) -> str:
        contact = classified.get("contact", {})
        author  = contact.get("author") or lead.get("authorName", "Unknown")
        content = lead.get("content", "")
        lines = [
            f"Category: {self.CATEGORY}",
            f"Author: {author}",
            "",
            "Original Post:",
            content,
            "",
            f"Contact: dm_requested={contact.get('dm_requested')}, "
            f"email={contact.get('email')}, phone={contact.get('phone')}",
        ]
        return "\n".join(lines)

    # ── Response parser ───────────────────────────────────────────────────────
    def _parse_response(self, resp: requests.Response) -> dict:
        text = ""
        try:
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError(f"No candidates in response: {data}")
            text = candidates[0]["content"]["parts"][0]["text"]
            args = json.loads(text)
        except json.JSONDecodeError as e:
            # Structured output failed — try to salvage a JSON object from the raw text
            print(f"[{self._label}] JSON parse failed ({e}) — attempting extraction")
            try:
                start = text.index("{")
                end = text.rindex("}") + 1
                args = json.loads(text[start:end])
                print(f"[{self._label}] Extracted JSON from raw text OK")
            except (ValueError, json.JSONDecodeError):
                # Last resort: treat whatever text came back as the outreach message
                print(f"[{self._label}] Extraction failed — storing raw text as outreach_message")
                args = {
                    "is_complete": False,
                    "missing_fields": [],
                    "outreach_message": text.strip(),
                    "investment_summary": "",
                    "location_insights": {}
                }
        except (KeyError, IndexError) as e:
            raise ValueError(
                f"Unexpected response structure ({e}): {resp.text[:500]}"
            ) from e

        # Safety net: blank out summary and insights when is_complete is false
        if not args.get("is_complete", False):
            args["investment_summary"] = ""
            args["location_insights"] = {}

        # Ensure location_insights is always a dict
        if not isinstance(args.get("location_insights"), dict):
            args["location_insights"] = {}

        return args

    # ── Public entry point ────────────────────────────────────────────────────
    def generate(self, classified: dict, lead: dict) -> dict:
        """
        Takes the classified lead dict and the original lead dict (with 'content'),
        returns outreach result: {is_complete, missing_fields, outreach_message,
        investment_summary, location_insights}
        """
        user_content = self._build_user_content(classified, lead)

        payload: dict = {
            "system_instruction": {"parts": [{"text": self.system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_content}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": self._build_schema(),
                **({"thinkingConfig": {"thinkingLevel": self.thinking_level}} if self.thinking_level else {})
            },
        }

        url = GEMINI_URL.format(model=self.model)
        headers = {"Content-Type": "application/json", "X-goog-api-key": self.api_key}

        resp = _request_with_retry(url, payload, headers, label=self._label)
        return self._parse_response(resp)
