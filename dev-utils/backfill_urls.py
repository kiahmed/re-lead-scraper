"""Backfill the `url` column on existing leads rows from hub run history.

The scraper webhook always includes each item's full post URL, but the hub
only started storing it on 2026-08-03. Logic App run history retains ~90
days of trigger payloads, so this walks every hub run, maps lead id → url,
and MERGE-upserts the url column onto matching rows (both RowKey schemes).

Usage:  python3 dev-utils/backfill_urls.py [--dry-run]
Needs:  az CLI logged in + AZURE_STORAGE_CONNECTION_STRING in .env
"""
import os
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "admin-api"))
from core import tables  # noqa: E402

# Azure identifiers come from .env — this repo is public, so nothing
# identifying is hardcoded here.
def _env(key: str) -> str:
    if os.environ.get(key):
        return os.environ[key]
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{key}=") and not line.startswith("#"):
                return line.partition("=")[2].strip().strip('"').strip("'")
    raise SystemExit(f"{key} is not set (env or .env)")


SUB = _env("AZURE_SUBSCRIPTION_ID")
RG = _env("AZURE_RESOURCE_GROUP")
HUB = "filterProcessCreativeLeads"
BASE = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Logic/workflows/{HUB}"


def _az(url: str):
    out = subprocess.check_output(["az", "rest", "--method", "GET", "--url", url, "-o", "json"])
    return json.loads(out)


def harvest() -> dict[str, str]:
    """Walk all hub runs (paginated) and collect id → url."""
    urls: dict[str, str] = {}
    page = f"{BASE}/runs?api-version=2016-06-01&$top=50"
    n_runs = 0
    while page:
        data = _az(page)
        for run in data.get("value", []):
            n_runs += 1
            link = run.get("properties", {}).get("trigger", {}).get("outputsLink", {}).get("uri")
            if not link:
                continue
            try:
                body = json.load(urllib.request.urlopen(link))
            except Exception as e:
                print(f"  skip run {run['name']}: {type(e).__name__}")
                continue
            for item in (body.get("body") or {}).get("items") or []:
                if item.get("id") and item.get("url"):
                    urls.setdefault(item["id"], item["url"])
        page = data.get("nextLink")
        print(f"  scanned {n_runs} runs, {len(urls)} unique lead urls so far")
    return urls


def harvest_samples() -> dict[str, str]:
    """Leads written by local/e2e runs never passed through the hub — their
    urls live in the dev-utils sample payloads instead."""
    urls: dict[str, str] = {}
    for f in sorted(Path(__file__).parent.glob("devi_leads_*.json")):
        try:
            for item in json.loads(f.read_text()).get("items", []):
                if item.get("id") and item.get("url"):
                    urls.setdefault(item["id"], item["url"])
        except (ValueError, OSError):
            continue
    print(f"  {len(urls)} urls from sample payload files")
    return urls


def main() -> None:
    dry = "--dry-run" in sys.argv
    print("Harvesting urls from hub run history…")
    urls = harvest()
    for lead_id, url in harvest_samples().items():
        urls.setdefault(lead_id, url)

    rows = tables.query(tables.TABLE_LEADS, "PartitionKey eq 'filtered'")
    updated = already = missing = 0
    for row in rows:
        if row.get("url"):
            already += 1
            continue
        lead_id = row.get("lead_id", "") or row.get("RowKey", "")
        url = urls.get(lead_id)
        if not url:
            missing += 1
            continue
        if not dry:
            tables.upsert(tables.TABLE_LEADS, {
                "PartitionKey": "filtered", "RowKey": row["RowKey"], "url": url,
            })
        updated += 1
    print(f"{'DRY RUN: would update' if dry else 'updated'} {updated} rows; "
          f"{already} already had urls; {missing} not found in run history "
          f"(older than retention — UI derives a story.php fallback from the id)")


if __name__ == "__main__":
    main()
