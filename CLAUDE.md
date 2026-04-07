# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An Azure serverless real estate lead qualification system. It receives Facebook real estate group posts via webhook, hard-filters them (HOA and city rules), then sends survivors to Google Gemini for AI-powered deal classification (Subject-To, Seller Finance, Fix & Flip, etc.) and routes results to per-category outreach agents.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in credentials
cp .env.example .env

# Run pipeline locally against a sample file (no Azure needed)
python3 main.py dev-utils/devi_leads_01.json

# Outreach smoke test (filter → classify → outreach agents, dumps JSON to dev-utils/run-logs/)
python3 dev-utils/test_outreach.py dev-utils/devi_leads_01.json

# E2E Azure test (fires hub, monitors hub + spoke runs, reads table, dumps to run-logs/)
python3 dev-utils/test_azure_e2e.py
python3 dev-utils/test_azure_e2e.py dev-utils/devi_leads_04.json dev-utils/devi_leads_05.json

# Clear leads table for a fresh test run
python3 dev-utils/clear_table.py           # clears all rows
python3 dev-utils/clear_table.py --dry-run # shows count only

# Sync values.yaml → Logic App workflow JSONs (run before every deploy)
python3 sync.py --apply          # generate deploy/workflows/*.json + write version record
python3 sync.py --check          # show sync status without writing anything

# Deploy to Azure
python3 deploy.py                # deploys deploy/main.bicep, writes URLs/keys to .env
python3 deploy.py --status       # show sync + version + Logic App status
python3 deploy.py --list         # list Logic Apps in the RG
```

## Python Project Structure

```
src/
  config.py                  # env-based config, loaded from .env
  agents/
    filter_agent.py          # city + HOA filter logic (mirrors Logic App Filter_Leads)
    classifier_agent.py      # Gemini classifier — tool calling, retry, response parsing
    table_store.py           # Azure Table shared memory (leads + appversions tables)
    outreach/
      base.py                # BaseOutreachAgent — responseSchema Gemini call + retry + parse fallback
      subject_to.py          # SubjectToAgent (CATEGORY = "Subject-To")
      seller_finance.py      # SellerFinanceAgent
      hybrid.py              # HybridAgent
      fix_and_flip.py        # FixAndFlipAgent
      jv_or_wholesale.py     # JVOrWholesaleAgent
      buyers_looking.py      # BuyersLookingAgent
      regular.py             # RegularAgent
      dispatcher.py          # routes classified leads → category agent
  sync/
    workflow_builder.py      # generates Logic App workflow JSONs from values.yaml
    version_tracker.py       # reads/writes version records via table_store
  runners/
    base.py                  # PipelineRunner abstract interface
    local_runner.py          # filter → table → classify → table → outreach → table
    azure_runner.py          # POSTs payload to Logic App trigger URL (RUN_MODE=azure)
  workflows/
    lead_pipeline.py         # selects runner from RUN_MODE, single run() entry point
main.py                      # CLI entry point — accepts JSON file or stdin
sync.py                      # CLI: sync values.yaml → deploy/workflows/*.json
deploy.py                    # deploys Bicep, writes URLs/keys to .env, records version
```

**Local vs Azure mode** — set `RUN_MODE` in `.env`:
- `local`: full pipeline in-process (filter → table → classify → table → outreach → table)
- `azure`: `AzureRunner` POSTs payload to `AZURE_LOGIC_APP_TRIGGER_URL`

## Azure Hub/Spoke Architecture

```
[Webhook POST]
      │
      ▼
filterProcessCreativeLeads (HUB Logic App)
      │
      ├─ 1. Filter_Leads (instant)
      │      City keyword match (Atlanta / Jacksonville) + HOA=$0 check
      │      Returns immediately 202 to caller — rest runs async
      │
      ├─ 2. For_Each_Filtered_Lead  ← concurrency = classify_batch_size (default 3)
      │      Processes up to 3 leads in parallel per batch:
      │
      │      Per lead:
      │      ├─ Upsert_Lead_To_Table
      │      ├─ Call_Gemini_Classify  (tool calling — classify_lead())
      │      ├─ Enforce_Selling_Intent_Gate
      │      ├─ Upsert_Classification_To_Table
      │      │
      │      └─ Condition_Route_To_Spoke
      │             │
      │      [actionable]──────────────────────────[Others]
      │             │                                  │
      │      Call_Spoke_Outreach               Upsert_Others_To_Table
      │      (HTTP POST, fire-and-forget)      (outreach_skipped=true)
      │      DisableAsyncPattern
      │             │
      │      Wait_Between_Spokes (10s)
      │      ← stagger across batches; all iterations
      │        in a batch wait concurrently, so next
      │        batch starts ~10s after spokes fire
      │
      └─ (loop advances to next batch when slowest iteration completes)


spoke-{category}-outreach  (7 Logic Apps, one per category)
      │
      ├─ HTTP trigger  ← called by hub (zero idle cost, no queue polling)
      ├─ Call_Gemini_Outreach  (responseSchema JSON mode)
      │      Counterparty persona per category
      │      is_complete = all required_fields present in extracted_info
      │      If complete   → casual insider message + ask for video/pics + call
      │      If incomplete → casual ask for specific missing fields only
      ├─ Parse_Outreach_Args  (@json(parts[0].text))
      ├─ Apply_Completeness_Gate
      │      blanks investment_summary + location_insights if is_complete=false
      │
      ├─ [success] Upsert_Outreach_To_Table  (errorMessage="none")
      └─ [failure] Handle_Outreach_Error     (errorMessage=<error>, outreach_skipped=true)
```

**Batch timing at default settings (classify_batch_size=3, spoke_interval=10s):**
```
t=0s   Batch 1: 3 leads classify in parallel (~5s) → fire spokes → wait 10s
t=15s  Batch 2: next 3 leads → fire spokes → wait 10s
t=30s  Batch 3: ...
```
9 leads ≈ 45s total hub time. Gemini 2.5 Flash peak load: ~18 RPM (limit: 2000 RPM).

**Sync + Deploy flow:**
1. Edit `values.yaml` (hub config, prompts, categories, required fields)
2. `python3 sync.py --apply` — regenerates `deploy/workflows/*.json`, records local hash
3. `python3 deploy.py` — deploys `deploy/main.bicep`, writes connection strings to `.env`

New agents: subclass `BaseOutreachAgent`, set `CATEGORY`, add persona + required_fields to `values.yaml outreach:` section, register in `dispatcher.py`.

## Azure Infrastructure

**Azure Resources** (`RELeadScraperGroup`, East US, subscription `fbdc966a-9476-484f-8935-55dee4eef4f3`):
- 8 Logic App workflows:
  - `filterProcessCreativeLeads` (hub)
  - `spoke-subject-to-outreach`
  - `spoke-seller-finance-outreach`
  - `spoke-hybrid-outreach`
  - `spoke-fix-flip-outreach`
  - `spoke-jv-wholesale-outreach`
  - `spoke-buyers-looking-outreach`
  - `spoke-regular-outreach`
- Log Analytics Workspace: `RELeadScraperLogAnalytics`

**Bicep structure** (`deploy/`):
- `main.bicep` — entry point; deploys storage + hub + 7 spokes
- `modules/storage.bicep` — Storage Account, tables, API connections
- `modules/hub.bicep` — filterProcessCreativeLeads Logic App
- `modules/spoke.bicep` — parameterized outreach spoke (instantiated 7×)
- `workflows/*.json` — **generated by sync.py from values.yaml** — do not edit by hand

`arm-template.bicep` / `arm-template.json` — legacy export, kept as reference only.

## values.yaml Structure

Central config — all tuneable behavior lives here. Loaded by agents at startup and by `workflow_builder.py` to generate Logic App JSONs.

```
hub:
  classify_batch_size       # parallel leads per foreach batch (default 3)
  spoke_interval_seconds    # wait after spoke fire before next batch (default 10)

filter:
  cities[]                  # keyword allowlist (case-insensitive match on lead.keywords[])
  hoa_zero_patterns[]       # regex patterns that mean HOA=$0 → lead passes

classifier:
  selling_intent_gate       # Step 1 system prompt — role detection before category
  categories{}              # Step 2 — category descriptions + signals
  contact_extraction        # Step 3 — contact field extraction rules
  extracted_info_rules      # Step 4 — dynamic JSON extraction rules per category

outreach:
  required_fields{}         # per-category fields that trigger is_complete=false if absent
                            # "location" key accepts city / neighborhood / ZIP / partial address
  personas{}                # per-category system prompts (counterparty role + tone)
                            # when complete: casual insider message, ask for video/pics + call
                            # when incomplete: short casual ask for missing fields only
```

## Spoke Outreach Design

Each spoke takes the **counterparty role** of the deal:

| Category | Spoke role |
|---|---|
| Subject-To | SubTo buyer (takes over mortgage payments) |
| Seller Finance | Buyer seeking owner carry |
| Hybrid | Morby Method buyer (assume + seller carry) |
| Fix & Flip | Rehabber / cash buyer |
| JV or Wholesale | Cash buyer reviewing assignment/JV |
| Buyers Looking | Deal finder / wholesaler bringing deals |
| Regular | Buyer evaluating conventional listing |

**Gemini call**: uses `responseSchema` JSON mode (not function calling). Per-category schema with typed field descriptions enforces output shape. Parse fallback chain in `base.py`: JSON parse → extract `{...}` from raw text → store raw text as `outreach_message`.

**`is_complete` logic**: Gemini checks whether all `required_fields` for the category are present in `extracted_info`. `location` field accepts any location signal (city, ZIP, partial address) — only flagged missing if the post has no location info at all.

**Table columns written per lead:**

| Column | Written by | Value |
|---|---|---|
| `outreach_message` | spoke | ready-to-send message |
| `investment_summary` | spoke | internal deal analysis (if complete) |
| `location_insights` | spoke | crime/poverty/rent/notes (if complete) |
| `missing_fields` | spoke | fields that triggered incomplete |
| `is_complete` | spoke | true/false |
| `outreach_skipped` | hub (Others) or spoke (error) | true/false |
| `errorMessage` | hub/spoke | "none" or error text |

## Key Data Shapes

**Inbound lead** (from Facebook scraper bot):
```json
{
  "items": [{
    "id": "facebook_<encoded>",
    "content": "post text",
    "keywords": ["Atlanta", ...],
    "authorName": "...",
    "groupName": "..."
  }]
}
```

**Classifier output** (hub → Azure Table + spoke payload):
```json
{
  "source_id": "facebook_<encoded>",
  "has_selling_intent": true,
  "category": "Subject-To|Seller Finance|Hybrid|Fix & Flip|JV or Wholesale|Buyers Looking|Regular|Others",
  "extracted_info": "{ ... }",
  "contact": { "author": "...", "email": null, "phone": null, "dm_requested": false }
}
```

**Spoke output** (written to Azure Table):
```json
{
  "is_complete": true,
  "missing_fields": [],
  "outreach_message": "casual insider message...",
  "investment_summary": "internal deal notes...",
  "location_insights": { "crime_index": "...", "poverty_rate": "...", "median_rent_estimate": "...", "market_notes": "..." },
  "errorMessage": "none"
}
```

## Design Notes

- `values.yaml` is the single source of truth — edit it, run `sync.py --apply`, then `deploy.py`
- The hard-filter stage exists to eliminate Gemini API costs — no AI calls until a lead passes both city and HOA checks
- Hub returns 202 immediately after filtering; all Gemini work runs async
- `dev-utils/` — sample leads (`devi_leads_*.json`), test scripts, run logs; keep non-production files here
- `prompt.txt` / `scratch-pad.txt` — legacy requirement docs and design history
