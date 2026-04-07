"""
Clears all rows from the leads Azure Table for a fresh test run.
Deletes in batches of 100 (Azure max per transaction, same partition key).

Usage:
  python3 dev-utils/clear_table.py           # clears leads table
  python3 dev-utils/clear_table.py --dry-run # shows count without deleting
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import src.config  # noqa: triggers load_dotenv
from src.config import AZURE_STORAGE_CONNECTION_STRING

if not AZURE_STORAGE_CONNECTION_STRING:
    print("ERROR: AZURE_STORAGE_CONNECTION_STRING not set in .env")
    sys.exit(1)

from azure.data.tables import TableServiceClient

DRY_RUN = "--dry-run" in sys.argv
TABLE   = "leads"

svc = TableServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
tbl = svc.get_table_client(TABLE)

entities = list(tbl.list_entities())
print(f"Found {len(entities)} row(s) in '{TABLE}' table")

if not entities:
    print("Nothing to clear.")
    sys.exit(0)

if DRY_RUN:
    print("Dry run — no rows deleted.")
    sys.exit(0)

# Batch deletes in chunks of 100 (Azure limit per transaction)
# All leads share PartitionKey="filtered" so they can be batched together
deleted = 0
for i in range(0, len(entities), 100):
    batch = [("delete", e) for e in entities[i:i + 100]]
    tbl.submit_transaction(batch)
    deleted += len(batch)
    print(f"  Deleted {deleted}/{len(entities)}...")

print(f"Done — {deleted} row(s) cleared from '{TABLE}'.")
