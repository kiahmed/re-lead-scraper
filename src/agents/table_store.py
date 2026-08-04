"""
Azure Table Storage shared memory layer for the lead pipeline.

Tables:
  leads        — one row per lead, enriched across three pipeline stages
  appversions  — version tracking for sync/deploy state

Lead lifecycle upserts (leads table):
  upsert_filtered_lead()       — after filter stage
  enrich_with_classification() — after Gemini classifier
  enrich_with_outreach()       — after category outreach agent

Version tracking (appversions table):
  upsert_local_version()       — after sync.py --apply
  update_deployed_version()    — after successful deploy
  get_version()                — read current version record

All operations are no-ops (with a warning) when
AZURE_STORAGE_CONNECTION_STRING is not set, so local dev without
Azure storage still works.

Row key encoding: lead IDs contain base64 characters (+/=) that are
invalid in Azure Table keys, so they are URL-encoded before storage.
"""
import json
import os
from datetime import datetime, timezone
from urllib.parse import quote

from azure.data.tables import TableServiceClient, UpdateMode

TABLE_LEADS = "leads"
TABLE_VERSIONS = "appversions"
TABLE_CONFIG = "config"
_VERSION_PK = "pipeline"
_VERSION_RK = "config"

# ── Client init ───────────────────────────────────────────────────────────────
_conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
_client: TableServiceClient | None = None

if _conn_str:
    try:
        _client = TableServiceClient.from_connection_string(_conn_str)
        _client.create_table_if_not_exists(TABLE_LEADS)
        _client.create_table_if_not_exists(TABLE_VERSIONS)
        _client.create_table_if_not_exists(TABLE_CONFIG)
    except Exception as e:
        print(f"[table_store] WARNING: failed to init Azure Table client: {e}")
        _client = None
else:
    print("[table_store] WARNING: AZURE_STORAGE_CONNECTION_STRING not set — skipping table ops")


def _table(name: str):
    if _client is None:
        return None
    return _client.get_table_client(name)


def _row_key(lead_id: str) -> str:
    """URL-encode ID to satisfy Azure Table row key character restrictions."""
    return quote(lead_id, safe="")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_upsert(table_name: str, entity: dict) -> None:
    tbl = _table(table_name)
    if tbl is None:
        return
    try:
        tbl.upsert_entity(entity, mode=UpdateMode.MERGE)
    except Exception as e:
        print(f"[table_store] WARNING: upsert failed for {entity.get('RowKey')} in {table_name}: {e}")


def _safe_get(table_name: str, partition_key: str, row_key: str) -> dict | None:
    tbl = _table(table_name)
    if tbl is None:
        return None
    try:
        return dict(tbl.get_entity(partition_key=partition_key, row_key=row_key))
    except Exception:
        return None


# ── Lead lifecycle (leads table) ──────────────────────────────────────────────
def upsert_filtered_lead(lead: dict) -> None:
    """Store a filtered lead. Called once per lead that passes the filter."""
    lead_id = lead.get("id", "")
    if not lead_id:
        return
    _safe_upsert(TABLE_LEADS, {
        "PartitionKey": "filtered",
        "RowKey": _row_key(lead_id),
        "lead_id": lead_id,
        "content": lead.get("content", ""),
        "keywords": json.dumps(lead.get("keywords", [])),
        "authorName": lead.get("authorName", ""),
        "groupName": lead.get("groupName", ""),
        "url": lead.get("url", ""),
        "stored_at": _now(),
    })


def enrich_with_classification(classified: dict) -> None:
    """Merge classifier output into the lead's table row."""
    source_id = classified.get("source_id", "")
    if not source_id:
        return
    _safe_upsert(TABLE_LEADS, {
        "PartitionKey": "filtered",
        "RowKey": _row_key(source_id),
        "has_selling_intent": classified.get("has_selling_intent"),
        "category": classified.get("category", ""),
        "extracted_info": classified.get("extracted_info", ""),
        "contact": json.dumps(classified.get("contact", {})),
        "classified_at": _now(),
    })


def enrich_with_outreach(source_id: str, outreach: dict | None) -> None:
    """Merge outreach agent output into the lead's table row."""
    if not source_id:
        return
    if outreach is None:
        # Write full schema with empty defaults so every row has the same columns
        _safe_upsert(TABLE_LEADS, {
            "PartitionKey":     "filtered",
            "RowKey":           _row_key(source_id),
            "outreach_skipped": True,
            "is_complete":      False,
            "missing_fields":   json.dumps([]),
            "outreach_message": "",
            "investment_summary": "",
            "location_insights":  json.dumps({}),
            "outreach_at":      _now(),
        })
        return
    _safe_upsert(TABLE_LEADS, {
        "PartitionKey": "filtered",
        "RowKey": _row_key(source_id),
        "outreach_skipped": False,
        "is_complete": outreach.get("is_complete"),
        "missing_fields": json.dumps(outreach.get("missing_fields", [])),
        "outreach_message": outreach.get("outreach_message", ""),
        "investment_summary": outreach.get("investment_summary", ""),
        "location_insights": json.dumps(outreach.get("location_insights", {})),
        "outreach_at": _now(),
    })


# ── Version tracking (appversions table) ─────────────────────────────────────
def upsert_local_version(local_hash: str, categories: list[str], label: str = "") -> None:
    """Write local (pre-deploy) version record after sync --apply."""
    _safe_upsert(TABLE_VERSIONS, {
        "PartitionKey": _VERSION_PK,
        "RowKey": _VERSION_RK,
        "local_hash": local_hash,
        "local_label": label,
        "categories": json.dumps(categories),
        "synced_at": _now(),
        "status": "out-of-sync",  # set to in-sync after successful deploy
    })


def update_deployed_version(deployed_hash: str) -> None:
    """Mark the deployed version after a successful deploy."""
    _safe_upsert(TABLE_VERSIONS, {
        "PartitionKey": _VERSION_PK,
        "RowKey": _VERSION_RK,
        "deployed_hash": deployed_hash,
        "deployed_at": _now(),
        "status": "in-sync",
    })


def get_version() -> dict | None:
    """Return the current version record, or None if not yet created."""
    return _safe_get(TABLE_VERSIONS, _VERSION_PK, _VERSION_RK)


# ── Config table (runtime secrets) ──────────────────────────────────────────
_CONFIG_PK = "secrets"


def upsert_config(key: str, value: str) -> None:
    """Store a key-value pair in the config table (e.g. geminiApiKey)."""
    _safe_upsert(TABLE_CONFIG, {
        "PartitionKey": _CONFIG_PK,
        "RowKey": key,
        "Value": value,
        "updated_at": _now(),
    })


def get_config(key: str) -> str | None:
    """Read a config value. Returns None if missing or table unavailable."""
    row = _safe_get(TABLE_CONFIG, _CONFIG_PK, key)
    return row.get("Value") if row else None
