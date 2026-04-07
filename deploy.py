"""
Deploy the lead pipeline Bicep template to Azure.

Usage:
  python3 deploy.py                    # deploy deploy/main.bicep (default)
  python3 deploy.py --bicep <file>     # deploy a specific Bicep file
  python3 deploy.py --mode Complete    # full replace (careful)
  python3 deploy.py --list             # list Logic Apps in the resource group
  python3 deploy.py --status           # show sync + version status (no deploy)

Deploy flow:
  1. Check sync status — warn if values.yaml changes haven't been synced yet
     (run 'python3 sync.py --apply' first if out of sync)
  2. Run 'az deployment group create' with deploy/main.bicep
  3. Parse deployment outputs (hub trigger URL, storage account name)
  4. Write AZURE_LOGIC_APP_TRIGGER_URL to .env
  5. Write AZURE_STORAGE_CONNECTION_STRING to .env
  6. Mark deployed version in Azure Table (appversions)

Separate from sync.py by design — sync generates Logic App workflow JSONs from
values.yaml; deploy pushes them to Azure. Run sync before deploy when
classifier prompts, categories, or outreach personas have changed.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from azure.identity import ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.logic import LogicManagementClient
from azure.mgmt.storage import StorageManagementClient

from src.config import (
    AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID,
    AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP,
)
from src.sync.version_tracker import compute_local_hash

HUB_LOGIC_APP_NAME = "filterProcessCreativeLeads"
HUB_TRIGGER_NAME = "When_an_HTTP_request_is_received"
ENV_FILE = Path(".env")
WORKFLOWS_DIR = Path("deploy/workflows")
REQUIRED_WORKFLOWS = ["hub-workflow.json"] + [
    f"spoke-{slug}-workflow.json"
    for slug in ["subject-to", "seller-finance", "hybrid", "fix-flip",
                 "jv-wholesale", "buyers-looking", "regular"]
]


# ── Azure credential ──────────────────────────────────────────────────────────
def _credential():
    return ClientSecretCredential(
        tenant_id=AZURE_TENANT_ID,
        client_id=AZURE_CLIENT_ID,
        client_secret=AZURE_CLIENT_SECRET,
    )


# ── .env helpers ──────────────────────────────────────────────────────────────
def update_env(key: str, value: str):
    """Update or append a key=value line in .env."""
    if not ENV_FILE.exists():
        ENV_FILE.write_text(f"{key}={value}\n")
        return
    lines = ENV_FILE.read_text().splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
            lines[i] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n")


# ── Pre-deploy checks ─────────────────────────────────────────────────────────
def check_sync_status() -> bool:
    """Return True if workflow files exist and hash matches last sync. Warn if not."""
    missing = [f for f in REQUIRED_WORKFLOWS if not (WORKFLOWS_DIR / f).exists()]
    if missing:
        print("ERROR: Missing workflow JSON files. Run 'python3 sync.py --apply' first.")
        for f in missing:
            print(f"  deploy/workflows/{f}")
        return False

    # Check if values.yaml changed since last sync (non-blocking, just warn)
    try:
        from src.agents import table_store
        record = table_store.get_version()
        if record:
            local_hash = compute_local_hash()
            synced_hash = record.get("local_hash", "")
            if local_hash != synced_hash:
                print("WARNING: values.yaml has changed since last sync.")
                print("  Run 'python3 sync.py --apply' to regenerate workflow JSONs.")
                print("  Continuing with existing workflow files...")
    except Exception:
        pass  # version check is informational only

    return True


# ── Deployment ────────────────────────────────────────────────────────────────
def get_gemini_api_key() -> str:
    """Read GEMINI_API_KEY from .env."""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def deploy(bicep_file: str, mode: str = "Incremental"):
    gemini_key = get_gemini_api_key()
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY not found in .env")
        sys.exit(1)

    cmd = [
        "az", "deployment", "group", "create",
        "--resource-group", AZURE_RESOURCE_GROUP,
        "--template-file", bicep_file,
        "--mode", mode,
        "--output", "json",
    ]
    print(f"Deploying {bicep_file} → {AZURE_RESOURCE_GROUP} ({mode})...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("Deployment FAILED:")
        print(result.stderr)
        sys.exit(1)

    print("Deployment succeeded.")

    # Parse outputs
    try:
        deployment_output = json.loads(result.stdout)
        outputs = deployment_output.get("properties", {}).get("outputs", {})
    except (json.JSONDecodeError, KeyError):
        outputs = {}

    # Hub trigger URL
    hub_url = outputs.get("hubTriggerUrl", {}).get("value")
    if hub_url:
        update_env("AZURE_LOGIC_APP_TRIGGER_URL", hub_url)
        print(f"AZURE_LOGIC_APP_TRIGGER_URL written to .env")
    else:
        # Fallback: fetch via SDK
        print("Fetching hub trigger URL via SDK...")
        hub_url = _fetch_hub_trigger_url()
        if hub_url:
            update_env("AZURE_LOGIC_APP_TRIGGER_URL", hub_url)
            print(f"AZURE_LOGIC_APP_TRIGGER_URL written to .env")

    # Storage account connection string
    storage_name = outputs.get("storageAccountName", {}).get("value")
    if storage_name:
        conn_str = _build_storage_connection_string(storage_name)
        if conn_str:
            update_env("AZURE_STORAGE_CONNECTION_STRING", conn_str)
            os.environ["AZURE_STORAGE_CONNECTION_STRING"] = conn_str
            print(f"AZURE_STORAGE_CONNECTION_STRING written to .env")

    # Seed Gemini API key into config table (read at runtime by Logic Apps)
    try:
        from src.agents import table_store
        existing = table_store.get_config("geminiApiKey")
        if existing != gemini_key:
            table_store.upsert_config("geminiApiKey", gemini_key)
            print("Gemini API key written to config table")
        else:
            print("Gemini API key unchanged — skipped config table update")
    except Exception as e:
        print(f"WARNING: could not seed config table: {e}")

    # Mark deployed version in Azure Table
    deployed_hash = compute_local_hash()
    try:
        from src.agents import table_store
        table_store.update_deployed_version(deployed_hash)
        print(f"Deployed version recorded in Azure Table (hash: {deployed_hash[:12]}...)")
    except Exception as e:
        print(f"WARNING: could not record deployed version: {e}")


def _fetch_hub_trigger_url() -> str:
    try:
        client = LogicManagementClient(_credential(), AZURE_SUBSCRIPTION_ID)
        callback = client.workflow_triggers.list_callback_url(
            resource_group_name=AZURE_RESOURCE_GROUP,
            workflow_name=HUB_LOGIC_APP_NAME,
            trigger_name=HUB_TRIGGER_NAME,
        )
        return callback.value
    except Exception as e:
        print(f"WARNING: could not fetch trigger URL: {e}")
        return ""


def _build_storage_connection_string(account_name: str) -> str:
    try:
        client = StorageManagementClient(_credential(), AZURE_SUBSCRIPTION_ID)
        keys = client.storage_accounts.list_keys(AZURE_RESOURCE_GROUP, account_name)
        key = keys.keys[0].value
        return (
            f"DefaultEndpointsProtocol=https;"
            f"AccountName={account_name};"
            f"AccountKey={key};"
            f"EndpointSuffix=core.windows.net"
        )
    except Exception as e:
        print(f"WARNING: could not build storage connection string: {e}")
        return ""


# ── Listing helpers ───────────────────────────────────────────────────────────
def list_logic_apps():
    client = ResourceManagementClient(_credential(), AZURE_SUBSCRIPTION_ID)
    resources = client.resources.list_by_resource_group(
        AZURE_RESOURCE_GROUP,
        filter="resourceType eq 'Microsoft.Logic/workflows'",
    )
    for r in resources:
        print(f"  {r.name}  [{r.location}]")


def show_status():
    print("── Deploy status ─────────────────────────────────────────────────────")
    missing = [f for f in REQUIRED_WORKFLOWS if not (WORKFLOWS_DIR / f).exists()]
    print(f"Workflow files : {'MISSING (' + str(len(missing)) + ')' if missing else 'OK (8 files)'}")

    try:
        from src.sync.version_tracker import VersionTracker
        tracker = VersionTracker()
        report = tracker.report()
        print(f"Local hash     : {report['local_hash']}")
        print(f"Deployed hash  : {report['deployed_hash']}")
        print(f"Synced at      : {report['synced_at']}")
        print(f"Deployed at    : {report['deployed_at']}")
        print(f"Status         : {report['status']}")
    except Exception as e:
        print(f"(Version status unavailable: {e})")

    print("\nLogic Apps in resource group:")
    try:
        list_logic_apps()
    except Exception as e:
        print(f"  (could not list: {e})")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy lead pipeline to Azure")
    parser.add_argument("--bicep", default="deploy/main.bicep", help="Bicep template to deploy")
    parser.add_argument("--mode", default="Incremental", choices=["Incremental", "Complete"])
    parser.add_argument("--list", action="store_true", help="List Logic Apps in the resource group")
    parser.add_argument("--status", action="store_true", help="Show sync + version status")
    args = parser.parse_args()

    if args.list:
        list_logic_apps()
    elif args.status:
        show_status()
    else:
        if not check_sync_status():
            sys.exit(1)
        deploy(args.bicep, args.mode)
