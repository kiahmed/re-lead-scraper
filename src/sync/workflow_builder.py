"""
Generates Azure Logic App workflow definition JSON files from values.yaml.

Outputs written to deploy/workflows/:
  hub-workflow.json            — filterProcessCreativeLeads
  spoke-{slug}-workflow.json  — one per outreach category (7 total)

Hub/spoke model (no queues — pure HTTP, zero idle cost):
  Hub:   filters → classifies → HTTP POST to each spoke (fire-and-forget)
  Spoke: HTTP trigger → Gemini outreach → Azure Table update

Called by sync.py --apply. Generated files are committed to git.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import yaml
from src.agents.classifier_agent import _build_system_prompt, _build_tool as _build_classify_tool

_VALUES_PATH = ROOT / "values.yaml"
_WORKFLOWS_DIR = ROOT / "deploy" / "workflows"

# Category name → spoke trigger URL parameter key (same key used in hub spokeUrls param)
# Mirrors _RETRY_ON_STATUS + MAX_RETRIES + exponential backoff in classifier_agent.py / base.py.
# Logic Apps doesn't support per-status-code intervals, so we use exponential with a base of 10s
# (matching the 5xx case) and a 5-minute ceiling (covers the 429 case: 60s * 2^2 = 240s).
# Logic Apps also natively respects Retry-After headers on 429, which compensates further.
# No-retry on 4xx (except 408/429) is Logic Apps default behaviour — matches _NO_RETRY_STATUS.
_GEMINI_RETRY_POLICY = {
    "type": "exponential",
    "count": 4,
    "interval": "PT30S",
    "minimumInterval": "PT30S",
    "maximumInterval": "PT10M"
}

# Action that fetches the Gemini API key from the config table at runtime,
# so the key never appears in Bicep params, ARM templates, or git history.
_FETCH_API_KEY_ACTION = {
    "type": "ApiConnection",
    "inputs": {
        "host": {"connection": {"name": "@parameters('$connections')['azuretables']['connectionId']"}},
        "method": "get",
        "path": "/Tables/@{encodeURIComponent('config')}/entities(PartitionKey='@{encodeURIComponent('secrets')}',RowKey='@{encodeURIComponent('geminiApiKey')}')"
    },
    "runAfter": {}
}

# ── Per-category outreach responseSchema ─────────────────────────────────────
_OUTREACH_MSG_DESC = {
    "Subject-To":    "Missing fields: ask only for absent items, 1-2 lines, investor tone. All present: genuine interest + ask for walkthrough video or pics + when to hop on a quick call. Short and real.",
    "Seller Finance":"Missing fields: ask only for absent items, concise. All present: genuine interest + ask for photos or walkthrough video + when works for a 10-minute call. Conversational.",
    "Hybrid":        "Missing fields: ask only for the gaps, casual like texting a buyer network contact. All present: show you know the Morby Method structure + interest + ask for video or pics + when to talk numbers.",
    "Fix & Flip":    "Missing fields: ask only for what's absent, brief, rehabber tone. All present: interested and active in the area + ask for photos or walkthrough video + when to connect. Like texting a wholesaler.",
    "JV or Wholesale":"Missing fields: ask only for what's absent, like following up with a wholesaler. All present: express interest + ask for photos or video + when to jump on a quick call. Serious cash buyer tone.",
    "Buyers Looking":"Missing fields: ask only for what's absent, casual. All present: confirm you've noted their criteria and actively work deals in their market. 1-2 lines, no pitch.",
    "Regular":       "Missing fields: ask only for what's absent, short and casual. All present: genuine interest + ask for photos or walkthrough video + when they're free for a quick call. Conversational.",
}

_INVESTMENT_SUMMARY_DESC = {
    "Subject-To":      "PITI vs rent spread, rate advantage, occupancy context. Empty string when is_complete=false.",
    "Seller Finance":  "LTV estimate, effective rate, monthly cash flow at stated terms, risk flags. Empty string when is_complete=false.",
    "Hybrid":          "Blended monthly payment (PITI + seller carry), total acquisition cost, cash flow at current rent, blended rate. Empty string when is_complete=false.",
    "Fix & Flip":      "MAO at 70% ARV minus estimated rehab, spread vs asking, condition complexity gut-check. Empty string when is_complete=false.",
    "JV or Wholesale": "Gross spread (ARV minus asking), work complexity estimate, timeline or deal structure notes. Empty string when is_complete=false.",
    "Buyers Looking":  "Always empty string.",
    "Regular":         "Price context, rough cap rate if numbers support it, red flags. Empty string when is_complete=false.",
}


def _build_outreach_schema(category: str, required_fields: list) -> dict:
    """Per-category responseSchema for the Gemini outreach call."""
    fields_list = json.dumps(required_fields)
    return {
        "type": "OBJECT",
        "properties": {
            "is_complete": {
                "type": "BOOLEAN",
                "description": f"True only if all of {fields_list} can be determined from the original post."
            },
            "missing_fields": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": f"Names of fields from {fields_list} that cannot be determined from the post. Empty array when is_complete is true."
            },
            "outreach_message": {
                "type": "STRING",
                "description": _OUTREACH_MSG_DESC.get(category, "Short casual message to the counterparty.")
            },
            "investment_summary": {
                "type": "STRING",
                "description": _INVESTMENT_SUMMARY_DESC.get(category, "Internal deal analysis. Empty string when is_complete is false.")
            },
            "location_insights": {
                "type": "OBJECT",
                "properties": {
                    "crime_index":           {"type": "STRING"},
                    "poverty_rate":          {"type": "STRING"},
                    "population_growth_rate":{"type": "STRING"},
                    "median_rent_estimate":  {"type": "STRING"},
                    "market_notes":          {"type": "STRING"}
                },
                "description": "Location context from address or ZIP using training knowledge. Empty object when is_complete is false or category is Buyers Looking."
            }
        },
        "required": ["is_complete", "missing_fields", "outreach_message", "investment_summary", "location_insights"]
    }


CATEGORY_SLUG = {
    "Subject-To":      "subject-to",
    "Seller Finance":  "seller-finance",
    "Hybrid":          "hybrid",
    "Fix & Flip":      "fix-flip",
    "JV or Wholesale": "jv-wholesale",
    "Buyers Looking":  "buyers-looking",
    "Regular":         "regular",
}


def _load_values() -> dict:
    with open(_VALUES_PATH) as f:
        return yaml.safe_load(f)


# ── Hub workflow ──────────────────────────────────────────────────────────────
def _build_hub_workflow(cfg: dict) -> dict:
    hub_cfg = cfg.get("hub", {})
    classify_batch_size    = hub_cfg.get("classify_batch_size", 3)
    spoke_interval_seconds = hub_cfg.get("spoke_interval_seconds", 10)
    classifier_cfg = cfg["classifier"]
    system_prompt = _build_system_prompt(classifier_cfg)
    tool_declaration = _build_classify_tool(classifier_cfg)

    # Build city filter dynamically from values.yaml — covers all configured cities
    cities = cfg.get("filter", {}).get("cities", ["atlanta"])
    city_checks = ",".join(
        f"contains(toLower(string(item()?['keywords'])),'{c.lower()}')"
        for c in cities
    )
    filter_where = (
        f"@and("
        f"or({city_checks}),"
        "or("
        "not(contains(toLower(item()?['content']),'hoa')),"
        "contains(toLower(replace(item()?['content'],' ','')),concat('hoa:$0')),"
        "contains(toLower(replace(item()?['content'],' ','')),concat('hoa=$0')),"
        "contains(toLower(replace(item()?['content'],' ','')),concat('hoa:0')),"
        "contains(toLower(replace(item()?['content'],' ','')),concat('hoa=0')),"
        "contains(toLower(item()?['content']),'no hoa'),"
        "contains(toLower(item()?['content']),'hoa none')"
        ")"
        ")"
    )

    gemini_payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{
            "role": "user",
            "parts": [{"text": (
                "@{concat("
                "'post#1\\n-------\\nId:', items('For_Each_Filtered_Lead')?['id'],"
                "'\\nContent:', items('For_Each_Filtered_Lead')?['content'],"
                "'\\nAuthor:', items('For_Each_Filtered_Lead')?['authorName']"
                ")}"
            )}]
        }],
        "tools": [tool_declaration],
        "tool_config": {
            "function_calling_config": {
                "mode": "ANY",
                "allowed_function_names": ["classify_lead"]
            }
        }
    }

    return {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "parameters": {
            "$connections": {"defaultValue": {}, "type": "Object"},
            "geminiModel":     {"defaultValue": "gemini-2.5-flash", "type": "String"},
            "storageTableName": {"defaultValue": "leads", "type": "String"},
            # Map of category name → spoke HTTP trigger URL, populated at deploy time
            "spokeUrls":       {"defaultValue": {}, "type": "Object"}
        },
        "triggers": {
            "When_an_HTTP_request_is_received": {
                "type": "Request",
                "kind": "Http",
                "description": "Webhook called by the external Facebook lead scraper bot",
                "inputs": {
                    "method": "POST",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id":          {"type": "string"},
                                        "content":     {"type": "string"},
                                        "keywords":    {"type": "array", "items": {"type": "string"}},
                                        "authorName":  {"type": "string"},
                                        "groupName":   {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "actions": {
            "Fetch_Api_Key": _FETCH_API_KEY_ACTION,
            "Filter_Leads": {
                "type": "Query",
                "inputs": {
                    "from": "@triggerBody()?['items']",
                    "where": filter_where
                },
                "runAfter": {}
            },
            "Condition_Has_Leads": {
                "type": "If",
                "expression": {
                    "and": [{"greater": ["@length(body('Filter_Leads'))", 0]}]
                },
                "actions": {
                    "For_Each_Filtered_Lead": {
                        "type": "Foreach",
                        "foreach": "@body('Filter_Leads')",
                        "runtimeConfiguration": {"concurrency": {"repetitions": classify_batch_size}},
                        "actions": {
                            "Upsert_Lead_To_Table": {
                                "type": "ApiConnection",
                                "inputs": {
                                    "host": {"connection": {"name": "@parameters('$connections')['azuretables']['connectionId']"}},
                                    "method": "patch",
                                    "path": "/Tables/@{encodeURIComponent(parameters('storageTableName'))}/entities(PartitionKey='@{encodeURIComponent('filtered')}',RowKey='@{encodeURIComponent(items('For_Each_Filtered_Lead')?['id'])}')",
                                    "body": {
                                        "lead_id":    "@items('For_Each_Filtered_Lead')?['id']",
                                        "content":    "@items('For_Each_Filtered_Lead')?['content']",
                                        "authorName": "@items('For_Each_Filtered_Lead')?['authorName']",
                                        "groupName":  "@{coalesce(items('For_Each_Filtered_Lead')?['groupName'], '')}",
                                        "keywords":   "@{string(items('For_Each_Filtered_Lead')?['keywords'])}",
                                        "stored_at":  "@{utcNow()}"
                                    }
                                },
                                "runAfter": {}
                            },
                            "Call_Gemini_Classify": {
                                "type": "Http",
                                "inputs": {
                                    "method": "POST",
                                    "uri": "@{concat('https://generativelanguage.googleapis.com/v1beta/models/', parameters('geminiModel'), ':generateContent')}",
                                    "headers": {
                                        "Content-Type": "application/json",
                                        "X-goog-api-key": "@body('Fetch_Api_Key')?['Value']"
                                    },
                                    "body": gemini_payload,
                                    "retryPolicy": _GEMINI_RETRY_POLICY
                                },
                                "runAfter": {"Upsert_Lead_To_Table": ["Succeeded"]}
                            },
                            "Parse_Classify_Args": {
                                "type": "Compose",
                                "inputs": "@body('Call_Gemini_Classify')['candidates'][0]['content']['parts'][0]['functionCall']['args']",
                                "runAfter": {"Call_Gemini_Classify": ["Succeeded"]}
                            },
                            # Mirrors _parse_tool_response selling-intent gate in classifier_agent.py:
                            # non-sellers that aren't "Buyers Looking" must be forced to "Others".
                            "Enforce_Selling_Intent_Gate": {
                                "type": "Compose",
                                "inputs": (
                                    "@if("
                                    "and("
                                    "not(outputs('Parse_Classify_Args')?['has_selling_intent']),"
                                    "not(or("
                                    "equals(outputs('Parse_Classify_Args')?['category'],'Others'),"
                                    "equals(outputs('Parse_Classify_Args')?['category'],'Buyers Looking')"
                                    "))"
                                    "),"
                                    "'Others',"
                                    "outputs('Parse_Classify_Args')?['category']"
                                    ")"
                                ),
                                "runAfter": {"Parse_Classify_Args": ["Succeeded"]}
                            },
                            "Upsert_Classification_To_Table": {
                                "type": "ApiConnection",
                                "inputs": {
                                    "host": {"connection": {"name": "@parameters('$connections')['azuretables']['connectionId']"}},
                                    "method": "patch",
                                    "path": "/Tables/@{encodeURIComponent(parameters('storageTableName'))}/entities(PartitionKey='@{encodeURIComponent('filtered')}',RowKey='@{encodeURIComponent(items('For_Each_Filtered_Lead')?['id'])}')",
                                    "body": {
                                        "has_selling_intent": "@{outputs('Parse_Classify_Args')?['has_selling_intent']}",
                                        "category":           "@{outputs('Enforce_Selling_Intent_Gate')}",
                                        "extracted_info":     "@{string(coalesce(outputs('Parse_Classify_Args')?['extracted_info'], '{}'))}",
                                        "contact":            "@{string(outputs('Parse_Classify_Args')?['contact'])}",
                                        "classified_at":      "@{utcNow()}"
                                    }
                                },
                                "runAfter": {"Enforce_Selling_Intent_Gate": ["Succeeded"]}
                            },
                            # Fire-and-forget: POST to spoke, don't wait for completion
                            "Condition_Route_To_Spoke": {
                                "type": "If",
                                "expression": {
                                    "and": [{
                                        "not": {"equals": ["@outputs('Enforce_Selling_Intent_Gate')", "Others"]}
                                    }]
                                },
                                "actions": {
                                    "Call_Spoke_Outreach": {
                                        "type": "Http",
                                        "description": "Fire-and-forget: hub does not wait for spoke to finish",
                                        "inputs": {
                                            "method": "POST",
                                            "uri": "@parameters('spokeUrls')[outputs('Enforce_Selling_Intent_Gate')]",
                                            "headers": {"Content-Type": "application/json"},
                                            "body": {
                                                "lead_id": "@items('For_Each_Filtered_Lead')?['id']"
                                            }
                                        },
                                        "operationOptions": "DisableAsyncPattern",
                                        "runAfter": {}
                                    },
                                    # Throttle spoke calls — wait 60s after each fire so
                                    # Gemini requests from concurrent spokes are staggered.
                                    # Runs even if the spoke POST failed to avoid tight loops.
                                    "Wait_Between_Spokes": {
                                        "type": "Wait",
                                        "inputs": {
                                            "interval": {"count": spoke_interval_seconds, "unit": "Second"}
                                        },
                                        "runAfter": {
                                            "Call_Spoke_Outreach": ["Succeeded", "Failed"]
                                        }
                                    }
                                },
                                "else": {
                                    "actions": {
                                        # Others leads have no spoke — mark outreach as
                                        # skipped in the table so every row is complete.
                                        "Upsert_Others_To_Table": {
                                            "type": "ApiConnection",
                                            "inputs": {
                                                "host": {"connection": {"name": "@parameters('$connections')['azuretables']['connectionId']"}},
                                                "method": "patch",
                                                "path": "/Tables/@{encodeURIComponent(parameters('storageTableName'))}/entities(PartitionKey='@{encodeURIComponent('filtered')}',RowKey='@{encodeURIComponent(items('For_Each_Filtered_Lead')?['id'])}')",
                                                "body": {
                                                    "outreach_skipped":   True,
                                                    "is_complete":        False,
                                                    "missing_fields":     "[]",
                                                    "outreach_message":   "",
                                                    "investment_summary": "",
                                                    "location_insights":  "{}",
                                                    "errorMessage":       "none",
                                                    "outreach_at":        "@{utcNow()}"
                                                }
                                            },
                                            "runAfter": {}
                                        }
                                    }
                                },
                                "runAfter": {"Upsert_Classification_To_Table": ["Succeeded"]}
                            }
                        },
                        "runAfter": {}
                    }
                },
                "else": {
                    "actions": {
                        "No_Leads_Passed_Filter": {
                            "type": "Compose",
                            "inputs": "No leads passed city/HOA filter"
                        }
                    }
                },
                "runAfter": {"Filter_Leads": ["Succeeded"], "Fetch_Api_Key": ["Succeeded"]}
            },
            # Response fires immediately after Filter_Leads so the caller
            # gets 202 without waiting for Gemini calls. Condition_Has_Leads
            # runs in parallel and does all heavy processing asynchronously.
            "Response": {
                "type": "Response",
                "kind": "Http",
                "inputs": {
                    "statusCode": 202,
                    "body": {
                        "filtered": "@length(body('Filter_Leads'))",
                        "status": "accepted"
                    }
                },
                "runAfter": {"Filter_Leads": ["Succeeded"]}
            }
        },
        "outputs": {}
    }


# ── Spoke workflow ────────────────────────────────────────────────────────────
def _build_spoke_workflow(category: str, cfg: dict) -> dict:
    outreach_cfg = cfg["outreach"]
    system_prompt = outreach_cfg["personas"][category]["system_prompt"].strip()
    required_fields = outreach_cfg["required_fields"].get(category, [])

    # Hub sends only lead_id; spoke fetches the full row (original content +
    # classification) from the table and passes it directly to Gemini.
    user_content_expr = (
        "@{concat("
        f"'Category: {category}\\nAuthor: ',"
        "body('Get_Lead_From_Table')?['authorName'],"
        "'\\n\\nOriginal Post:\\n',"
        "body('Get_Lead_From_Table')?['content'],"
        "'\\n\\nContact: ',"
        "body('Get_Lead_From_Table')?['contact']"
        ")}"
    )

    gemini_payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_content_expr}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _build_outreach_schema(category, required_fields)
        }
    }

    row_key_expr = "@{encodeURIComponent(triggerBody()?['lead_id'])}"

    return {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "parameters": {
            "$connections":     {"defaultValue": {}, "type": "Object"},
            "geminiModel":      {"defaultValue": "gemini-2.5-flash", "type": "String"},
            "storageTableName": {"defaultValue": "leads", "type": "String"}
        },
        "triggers": {
            # HTTP trigger — zero idle cost, only runs when hub calls it
            "When_an_HTTP_request_is_received": {
                "type": "Request",
                "kind": "Http",
                "description": f"Called by hub Logic App after classifying a {category} lead",
                "inputs": {
                    "method": "POST",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "lead_id": {"type": "string"}
                        }
                    }
                }
            }
        },
        "actions": {
            "Fetch_Api_Key": _FETCH_API_KEY_ACTION,
            # Fetch the full lead row — original post content + classification
            # written by the hub before this spoke was triggered.
            "Get_Lead_From_Table": {
                "type": "ApiConnection",
                "inputs": {
                    "host": {"connection": {"name": "@parameters('$connections')['azuretables']['connectionId']"}},
                    "method": "get",
                    "path": f"/Tables/@{{encodeURIComponent(parameters('storageTableName'))}}/entities(PartitionKey='@{{encodeURIComponent('filtered')}}',RowKey='{row_key_expr}')",
                },
                "runAfter": {}
            },
            # Logic Apps returns 202 immediately to caller (hub) when HTTP trigger fires;
            # remaining actions run asynchronously in the background.
            "Call_Gemini_Outreach": {
                "type": "Http",
                "inputs": {
                    "method": "POST",
                    "uri": "@{concat('https://generativelanguage.googleapis.com/v1beta/models/', parameters('geminiModel'), ':generateContent')}",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-goog-api-key": "@body('Fetch_Api_Key')?['Value']"
                    },
                    "body": gemini_payload,
                    "retryPolicy": _GEMINI_RETRY_POLICY
                },
                "runAfter": {"Get_Lead_From_Table": ["Succeeded"], "Fetch_Api_Key": ["Succeeded"]}
            },
            "Parse_Outreach_Args": {
                "type": "Compose",
                "inputs": "@json(body('Call_Gemini_Outreach')['candidates'][0]['content']['parts'][0]['text'])",
                "runAfter": {"Call_Gemini_Outreach": ["Succeeded"]}
            },
            # Mirrors _parse_response safety net in base.py:
            # blank out investment_summary and location_insights when is_complete is false.
            "Apply_Completeness_Gate": {
                "type": "Compose",
                "inputs": {
                    "is_complete":        "@outputs('Parse_Outreach_Args')?['is_complete']",
                    "missing_fields":     "@outputs('Parse_Outreach_Args')?['missing_fields']",
                    "outreach_message":   "@outputs('Parse_Outreach_Args')?['outreach_message']",
                    "investment_summary": "@if(outputs('Parse_Outreach_Args')?['is_complete'], outputs('Parse_Outreach_Args')?['investment_summary'], '')",
                    "location_insights":  "@if(outputs('Parse_Outreach_Args')?['is_complete'], outputs('Parse_Outreach_Args')?['location_insights'], json('{}'))"
                },
                "runAfter": {"Parse_Outreach_Args": ["Succeeded"]}
            },
            "Upsert_Outreach_To_Table": {
                "type": "ApiConnection",
                "inputs": {
                    "host": {"connection": {"name": "@parameters('$connections')['azuretables']['connectionId']"}},
                    "method": "patch",
                    "path": f"/Tables/@{{encodeURIComponent(parameters('storageTableName'))}}/entities(PartitionKey='@{{encodeURIComponent('filtered')}}',RowKey='{row_key_expr}')",
                    "body": {
                        "outreach_skipped":   False,
                        "is_complete":        "@{outputs('Apply_Completeness_Gate')?['is_complete']}",
                        "missing_fields":     "@{string(outputs('Apply_Completeness_Gate')?['missing_fields'])}",
                        "outreach_message":   "@{outputs('Apply_Completeness_Gate')?['outreach_message']}",
                        "investment_summary": "@{outputs('Apply_Completeness_Gate')?['investment_summary']}",
                        "location_insights":  "@{string(outputs('Apply_Completeness_Gate')?['location_insights'])}",
                        "outreach_at":        "@{utcNow()}",
                        "errorMessage":       "none"
                    }
                },
                "runAfter": {"Apply_Completeness_Gate": ["Succeeded"]}
            },
            # Error handler — catches failures in table read, Gemini call, parse, or gate
            "Handle_Outreach_Error": {
                "type": "ApiConnection",
                "inputs": {
                    "host": {"connection": {"name": "@parameters('$connections')['azuretables']['connectionId']"}},
                    "method": "patch",
                    "path": f"/Tables/@{{encodeURIComponent(parameters('storageTableName'))}}/entities(PartitionKey='@{{encodeURIComponent('filtered')}}',RowKey='{row_key_expr}')",
                    "body": {
                        "outreach_skipped":   True,
                        "is_complete":        False,
                        "missing_fields":     "[]",
                        "outreach_message":   "",
                        "investment_summary": "",
                        "location_insights":  "{}",
                        "errorMessage": "@{coalesce(actions('Fetch_Api_Key')?['error']?['message'], actions('Get_Lead_From_Table')?['error']?['message'], actions('Call_Gemini_Outreach')?['error']?['message'], actions('Parse_Outreach_Args')?['error']?['message'], actions('Apply_Completeness_Gate')?['error']?['message'], 'Unknown outreach error')}",
                        "outreach_at": "@{utcNow()}"
                    }
                },
                "runAfter": {
                    "Fetch_Api_Key":           ["Failed"],
                    "Get_Lead_From_Table":     ["Failed"],
                    "Call_Gemini_Outreach":    ["Failed"],
                    "Parse_Outreach_Args":     ["Failed"],
                    "Apply_Completeness_Gate": ["Failed"]
                }
            }
        },
        "outputs": {}
    }


# ── Public API ────────────────────────────────────────────────────────────────
def build_all_workflows() -> dict[str, Path]:
    """Generate all workflow JSONs from values.yaml. Returns {name: path}."""
    _WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    cfg = _load_values()
    written = {}

    hub_path = _WORKFLOWS_DIR / "hub-workflow.json"
    hub_path.write_text(json.dumps(_build_hub_workflow(cfg), indent=2))
    written["hub"] = hub_path
    print(f"[workflow_builder] wrote {hub_path.name}")

    for category, slug in CATEGORY_SLUG.items():
        spoke_path = _WORKFLOWS_DIR / f"spoke-{slug}-workflow.json"
        spoke_path.write_text(json.dumps(_build_spoke_workflow(category, cfg), indent=2))
        written[f"spoke-{slug}"] = spoke_path
        print(f"[workflow_builder] wrote {spoke_path.name}")

    return written
