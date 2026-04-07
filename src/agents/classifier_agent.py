"""
Sends filtered leads to Gemini for deal classification using function/tool calling.

Why tool calling instead of responseSchema:
  - Output comes back as structured functionCall args — no markdown wrapping,
    no JSON text parsing, no field-name drift between runs.
  - The model MUST call classify_lead() for every post (mode: ANY).
  - has_selling_intent is an explicit reasoning field — forces the model to
    evaluate transaction intent before assigning a category.

Config (prompts, categories, filter rules) loaded from values.yaml.
"""
import json
import time
import yaml
import requests
from pathlib import Path
from requests.exceptions import Timeout, ConnectionError, ChunkedEncodingError

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_CONFIG_PATH = Path(__file__).parent.parent.parent / "values.yaml"

# ── Retry config ──────────────────────────────────────────────────────────────
_RETRY_ON_STATUS: dict[int, int] = {
    408: 10,   # Request Timeout       — base wait seconds
    429: 60,   # Rate Limited          — generous back-off
    500: 10,   # Internal Server Error
    502: 10,   # Bad Gateway
    503: 15,   # Service Unavailable
    504: 10,   # Gateway Timeout
}
_NO_RETRY_STATUS = {400, 401, 403, 404}
_RETRYABLE_EXCEPTIONS = (Timeout, ConnectionError, ChunkedEncodingError)
MAX_RETRIES = 3


# ── Config loader ─────────────────────────────────────────────────────────────
def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)["classifier"]


def _build_system_prompt(cfg: dict) -> str:
    """Assemble the full system prompt from YAML config sections."""
    category_block = "\n".join(
        f'  • {name}: {defn["description"].strip()}'
        for name, defn in cfg["categories"].items()
    )
    return (
        "You are a real estate investment analyst. "
        "For each post you receive, call classify_lead() exactly once.\n\n"
        f"{cfg['selling_intent_gate'].strip()}\n\n"
        "STEP 2 — CATEGORY DEFINITIONS (apply only when has_selling_intent = true):\n"
        f"{category_block}\n\n"
        f"STEP 3 — CONTACT EXTRACTION:\n{cfg['contact_extraction'].strip()}\n\n"
        f"STEP 4 — EXTRACTED INFO:\n{cfg['extracted_info_rules'].strip()}"
    )


def _build_tool(cfg: dict) -> dict:
    """Build the Gemini function declaration for classify_lead."""
    category_names = list(cfg["categories"].keys())
    return {
        "function_declarations": [
            {
                "name": "classify_lead",
                "description": (
                    "Classify a single real estate post. "
                    "Call this once per post. "
                    "Evaluate has_selling_intent first — if false, category must be 'Others'."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "has_selling_intent": {
                            "type": "BOOLEAN",
                            "description": (
                                "True if the poster is a SELLER or DEAL-MAKER: owner offering "
                                "a property, wholesaler assigning a contract, or investor "
                                "proposing a JV. False if the poster is a buyer, learner, "
                                "lender-seeker, or service provider."
                            ),
                        },
                        "category": {
                            "type": "STRING",
                            "enum": category_names,
                            "description": (
                                "When has_selling_intent is true: assign a seller category. "
                                "When has_selling_intent is false: assign 'Buyers Looking' "
                                "if actively seeking properties/deal flow, otherwise 'Others'."
                            ),
                        },
                        "extracted_info": {
                            "type": "STRING",
                            "description": (
                                "JSON-stringified object of deal details. "
                                "For Others: {\"summary\": \"<one sentence>\"}."
                            ),
                        },
                        "contact": {
                            "type": "OBJECT",
                            "properties": {
                                "author":       {"type": "STRING"},
                                "email":        {"type": "STRING"},
                                "phone":        {"type": "STRING"},
                                "website":      {"type": "STRING"},
                                "dm_requested": {"type": "BOOLEAN"},
                            },
                            "required": ["author"],
                        },
                    },
                    "required": ["has_selling_intent", "category", "extracted_info", "contact"],
                },
            }
        ]
    }


# ── Post formatter ────────────────────────────────────────────────────────────
def _format_posts(leads: list[dict]) -> str:
    parts = []
    for i, lead in enumerate(leads, 1):
        parts.append(
            f"post#{i}\n-------"
            f"Id:{lead['id']}\n"
            f"Content:{lead['content']}\n"
            f"Author:{lead.get('authorName', '')}"
        )
    return "\n\n".join(parts)


# ── HTTP retry ────────────────────────────────────────────────────────────────
def _request_with_retry(url: str, payload: dict, headers: dict, timeout: int = 60) -> requests.Response:
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        resp: requests.Response | None = None
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except _RETRYABLE_EXCEPTIONS as e:
            last_exc = e
            wait = 5 * (2 ** attempt)
            if attempt < MAX_RETRIES:
                print(f"[classifier] {type(e).__name__} — retrying in {wait}s "
                      f"(attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            raise

        if resp.status_code in _NO_RETRY_STATUS:
            resp.raise_for_status()

        if resp.status_code in _RETRY_ON_STATUS:
            wait = _RETRY_ON_STATUS[resp.status_code] * (2 ** attempt)
            if attempt < MAX_RETRIES:
                print(f"[classifier] HTTP {resp.status_code} — retrying in {wait}s "
                      f"(attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            resp.raise_for_status()

        resp.raise_for_status()
        return resp

    if last_exc:
        raise last_exc
    raise RuntimeError("Request failed after all retries")


# ── Response parser ───────────────────────────────────────────────────────────
def _parse_tool_response(resp: requests.Response) -> list[dict]:
    """Extract classify_lead() call arguments from a Gemini tool-call response."""
    try:
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError(f"Gemini returned no candidates. Response: {data}")
        parts = candidates[0]["content"]["parts"]
    except (KeyError, IndexError) as e:
        raise ValueError(
            f"Unexpected Gemini response structure ({e}): {resp.text[:500]}"
        ) from e

    results = []
    for part in parts:
        if "functionCall" not in part:
            continue
        fc = part["functionCall"]
        if fc.get("name") != "classify_lead":
            continue
        args = fc.get("args", {})

        # Enforce selling intent gate in post-processing as a safety net:
        # non-sellers can only be "Buyers Looking" or "Others"
        if not args.get("has_selling_intent", True):
            if args.get("category") not in ("Buyers Looking", "Others"):
                args["category"] = "Others"

        # Ensure extracted_info is always a JSON string
        ei = args.get("extracted_info", "")
        if isinstance(ei, dict):
            args["extracted_info"] = json.dumps(ei)
        elif not isinstance(ei, str):
            args["extracted_info"] = json.dumps({"summary": str(ei)})

        # Normalize contact dict — fill optional fields so callers never see None
        contact = args.get("contact")
        if not isinstance(contact, dict):
            contact = {}
        contact.setdefault("author", "")
        contact.setdefault("email", None)
        contact.setdefault("phone", None)
        contact.setdefault("website", None)
        contact.setdefault("dm_requested", False)
        args["contact"] = contact

        results.append(args)

    if not results:
        raise ValueError(
            f"Gemini made no classify_lead() calls. "
            f"finishReason: {candidates[0].get('finishReason')}. "
            f"Response: {resp.text[:500]}"
        )

    return results


# ── Public API ────────────────────────────────────────────────────────────────
def classify_leads(
    leads: list[dict],
    api_key: str,
    model: str = "gemini-1.5-flash",
    thinking_level: str = "",
) -> list[dict]:
    cfg = _load_config()

    # Tool calling replaces responseSchema — output is structured function call args
    payload: dict = {
        "system_instruction": {"parts": [{"text": _build_system_prompt(cfg)}]},
        "contents": [{"role": "user", "parts": [{"text": _format_posts(leads)}]}],
        "tools": [_build_tool(cfg)],
        "tool_config": {
            "function_calling_config": {
                "mode": "ANY",
                "allowed_function_names": ["classify_lead"],
            }
        },
    }

    # thinkingConfig only added when set — not all models support it
    if thinking_level:
        payload["generationConfig"] = {
            "thinkingConfig": {"thinkingLevel": thinking_level}
        }

    url = GEMINI_URL.format(model=model)
    headers = {"Content-Type": "application/json", "X-goog-api-key": api_key}

    resp = _request_with_retry(url, payload, headers)

    try:
        results = _parse_tool_response(resp)
    except ValueError as e:
        # Gemini returned no usable tool calls — mark all leads as Others rather than
        # crashing the entire batch and losing every lead silently.
        print(f"[classifier] Gemini returned no usable tool calls: {e}")
        return [
            {
                "source_id":         lead["id"],
                "has_selling_intent": False,
                "category":          "Others",
                "extracted_info":    json.dumps({"summary": "Classification failed — Gemini returned no tool calls"}),
                "contact": {
                    "author":       lead.get("authorName", ""),
                    "email":        None,
                    "phone":        None,
                    "website":      None,
                    "dm_requested": False,
                },
            }
            for lead in leads
        ]

    # source_id is assigned here from the authoritative lead id — Gemini never echoes it
    if len(results) != len(leads):
        print(f"[classifier] WARNING: expected {len(leads)} results, got {len(results)}")
    for i, result in enumerate(results):
        result["source_id"] = leads[i]["id"] if i < len(leads) else "unknown"

    return results
