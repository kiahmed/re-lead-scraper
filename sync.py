"""
Sync local values.yaml → Azure Logic App workflow JSON files.

Commands:
  python3 sync.py --apply   Generate/update deploy/workflows/*.json from values.yaml,
                            write local version record to Azure Table.
  python3 sync.py --check   Show sync status without writing anything.
  python3 sync.py --status  Alias for --check.

Run --apply before every deploy. deploy.py will warn if workflows are out of date.

What --apply does:
  1. Read values.yaml (classifier + outreach + filter sections)
  2. Compute SHA-256 hash of those sections
  3. Generate deploy/workflows/hub-workflow.json and 7 spoke workflow JSONs
  4. Write local_hash + synced_at to Azure Table appversions (if configured)
  5. Print summary of what changed

The generated workflow JSONs are committed to git — they represent the Logic App
state that will be deployed next. They also serve as a diff-friendly history of
what changed between versions.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import src.config  # noqa: F401 — triggers load_dotenv() before table_store is imported

from src.sync.workflow_builder import build_all_workflows, CATEGORY_SLUG
from src.sync.version_tracker import VersionTracker, compute_local_hash


def cmd_apply(args) -> int:
    print("── Sync: apply ──────────────────────────���───────────────────────────")

    # Build workflow JSONs
    written = build_all_workflows()
    print(f"\nGenerated {len(written)} workflow files:")
    for name, path in written.items():
        size = path.stat().st_size
        print(f"  {path.relative_to(ROOT)}  ({size:,} bytes)")

    # Write version record
    local_hash = compute_local_hash()
    print(f"\nLocal hash : {local_hash[:12]}...")

    tracker = VersionTracker()
    try:
        tracker.apply()
        print("Version record written to Azure Table (appversions).")
    except Exception as e:
        print(f"WARNING: could not write version record: {e}")
        print("(Table ops require AZURE_STORAGE_CONNECTION_STRING in .env)")

    print("\nDone. Run 'python3 deploy.py' to deploy.")
    return 0


def cmd_check(args) -> int:
    print("── Sync: status ─────────────────────────────────────────────────────")
    local_hash = compute_local_hash()

    # Check workflow files exist
    workflows_dir = ROOT / "deploy" / "workflows"
    expected = ["hub-workflow.json"] + [f"spoke-{slug}-workflow.json" for slug in CATEGORY_SLUG.values()]
    missing = [f for f in expected if not (workflows_dir / f).exists()]

    if missing:
        print(f"MISSING workflow files (run --apply):")
        for f in missing:
            print(f"  deploy/workflows/{f}")
    else:
        print(f"Workflow files : OK ({len(expected)} files present)")

    print(f"Local hash     : {local_hash[:12]}...")

    tracker = VersionTracker()
    try:
        report = tracker.report()
        print(f"Deployed hash  : {report['deployed_hash']}")
        print(f"Synced at      : {report['synced_at']}")
        print(f"Deployed at    : {report['deployed_at']}")
        print(f"Status         : {report['status']}")
        if report["in_sync"] and not missing:
            print("\n✓ Local config matches deployed version.")
        else:
            print("\n✗ Out of sync — run 'python3 sync.py --apply' then 'python3 deploy.py'.")
    except Exception as e:
        print(f"(Could not read version record from Azure Table: {e})")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync values.yaml → Logic App workflow JSONs")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="Generate workflows + write version record")
    group.add_argument("--check", "--status", action="store_true", help="Show sync status (read-only)")
    args = parser.parse_args()

    if args.apply:
        sys.exit(cmd_apply(args))
    else:
        sys.exit(cmd_check(args))
