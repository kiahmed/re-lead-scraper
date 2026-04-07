"""
Runs the full pipeline in-process — no Azure trigger required.
Use this during local development (RUN_MODE=local).

Pipeline stages:
  1. filter_leads        — city + HOA hard filter
  2. upsert_filtered     — store survivors in Azure Table (skipped if no storage creds)
  3. classify_leads      — Gemini classifier (tool calling)
  4. enrich_classified   — merge classification into Azure Table rows
  5. dispatch_outreach   — per-category Gemini outreach agents
  6. enrich_outreach     — merge outreach results into Azure Table rows

Return value: list of merged dicts — classifier fields + "outreach" key per lead.
Consumers that only read classifier fields (source_id, category, etc.) are unaffected.
"""
from .base import PipelineRunner
from ..agents.filter_agent import filter_leads
from ..agents.classifier_agent import classify_leads, _format_posts
from ..agents.outreach import dispatch_outreach
from ..agents import table_store


class LocalRunner(PipelineRunner):
    def __init__(self, gemini_api_key: str, gemini_model: str = "gemini-1.5-flash", thinking_level: str = ""):
        self.api_key = gemini_api_key
        self.model = gemini_model
        self.thinking_level = thinking_level

    def process(self, payload: dict) -> list[dict]:
        leads = payload.get("items", [])
        print(f"[local] received {len(leads)} leads")

        # ── Stage 1: Filter ───────────────────────────────────────────────────
        filtered = filter_leads(leads)
        print(f"[local] {len(filtered)} passed filter")

        if not filtered:
            return []

        formatted = _format_posts(filtered)
        print(f"[local] formatted posts:\n{formatted}\n")

        # ── Stage 2: Store filtered leads ─────────────────────────────────────
        for lead in filtered:
            table_store.upsert_filtered_lead(lead)

        # ── Stage 3: Classify ─────────────────────────────────────────────────
        classified = classify_leads(filtered, self.api_key, self.model, self.thinking_level)
        print(f"[local] classified {len(classified)} leads")

        # ── Stage 4: Enrich table with classification ─────────────────────────
        for result in classified:
            table_store.enrich_with_classification(result)

        # ── Stage 5: Outreach dispatch ────────────────────────────────────────
        print(f"[local] dispatching outreach for {len(classified)} leads...")
        leads_by_id = {lead["id"]: lead for lead in filtered}
        outreach_results = dispatch_outreach(
            classified, leads_by_id, self.api_key, self.model, self.thinking_level
        )

        # ── Stage 6: Enrich table with outreach + merge for return ────────────
        outreach_by_id = {r["source_id"]: r["outreach"] for r in outreach_results}

        merged = []
        for result in classified:
            sid = result["source_id"]
            outreach = outreach_by_id.get(sid)
            table_store.enrich_with_outreach(sid, outreach)
            merged.append({**result, "outreach": outreach})

        return merged
