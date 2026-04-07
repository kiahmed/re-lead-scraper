"""
Routes each classified lead to its category-specific outreach agent.

- "Others" leads are skipped — no Gemini call, outreach set to None.
- All other categories get a Gemini call via the appropriate agent.
- Errors per lead are caught and logged; that lead gets outreach=None
  so a single bad lead never aborts the rest of the batch.
"""
from .subject_to import SubjectToAgent
from .seller_finance import SellerFinanceAgent
from .hybrid import HybridAgent
from .fix_and_flip import FixAndFlipAgent
from .jv_or_wholesale import JVOrWholesaleAgent
from .buyers_looking import BuyersLookingAgent
from .regular import RegularAgent

CATEGORY_AGENT_MAP = {
    "Subject-To":      SubjectToAgent,
    "Seller Finance":  SellerFinanceAgent,
    "Hybrid":          HybridAgent,
    "Fix & Flip":      FixAndFlipAgent,
    "JV or Wholesale": JVOrWholesaleAgent,
    "Buyers Looking":  BuyersLookingAgent,
    "Regular":         RegularAgent,
}


def dispatch_outreach(
    classified_leads: list[dict],
    leads_by_id: dict[str, dict],
    api_key: str,
    model: str = "gemini-1.5-flash",
    thinking_level: str = "",
) -> list[dict]:
    """
    For each classified lead, call the matching outreach agent.
    leads_by_id maps lead id → original lead dict (with 'content').
    Returns a list of dicts: {"source_id": ..., "outreach": <result or None>}
    in the same order as the input.
    """
    results = []
    for classified in classified_leads:
        source_id = classified.get("source_id", "unknown")
        category  = classified.get("category", "")
        lead      = leads_by_id.get(source_id, {})

        if category == "Others":
            results.append({"source_id": source_id, "outreach": None})
            continue

        agent_class = CATEGORY_AGENT_MAP.get(category)
        if agent_class is None:
            print(f"[dispatcher] unknown category '{category}' for {source_id} — skipping outreach")
            results.append({"source_id": source_id, "outreach": None})
            continue

        try:
            agent = agent_class(api_key, model, thinking_level)
            outreach = agent.generate(classified, lead)
            print(f"[dispatcher] {category} | {source_id} | "
                  f"complete={outreach.get('is_complete')} | "
                  f"missing={outreach.get('missing_fields', [])}")
            results.append({"source_id": source_id, "outreach": outreach})
        except Exception as e:
            print(f"[dispatcher] ERROR for {source_id} ({category}): {e}")
            results.append({"source_id": source_id, "outreach": None})

    return results
