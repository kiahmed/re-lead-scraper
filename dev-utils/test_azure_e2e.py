"""
End-to-end Azure test: fires the hub Logic App for one or more test files,
monitors hub + spoke runs, reads Table Storage results, dumps to run-logs/.

Architecture:
  Hub processes leads in parallel batches of classify_batch_size=3 via a
  forEach concurrency loop. After each batch, a Wait_Between_Spokes delay of
  spoke_interval_seconds=10 staggers spoke Gemini calls.

  Spokes are HTTP-triggered by the hub (DisableAsyncPattern fire-and-forget).
  They start during the hub run and are often complete before hub finishes.
  Spoke monitoring scans for runs that started at or after the trigger time.

Usage:
  python3 dev-utils/test_azure_e2e.py
  python3 dev-utils/test_azure_e2e.py dev-utils/devi_leads_04.json [...]
"""
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import src.config  # noqa: triggers load_dotenv before anything reads os.environ
import requests
from azure.identity import ClientSecretCredential
from azure.mgmt.logic import LogicManagementClient
from azure.data.tables import TableServiceClient

from src.config import (
    AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID,
    AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP,
    AZURE_LOGIC_APP_TRIGGER_URL, AZURE_STORAGE_CONNECTION_STRING,
)

HUB_NAME = "filterProcessCreativeLeads"
SPOKE_NAMES = [
    "spoke-subject-to-outreach",
    "spoke-seller-finance-outreach",
    "spoke-hybrid-outreach",
    "spoke-fix-flip-outreach",
    "spoke-jv-wholesale-outreach",
    "spoke-buyers-looking-outreach",
    "spoke-regular-outreach",
]
# Human-readable category name per spoke
SPOKE_CATEGORY = {
    "spoke-subject-to-outreach":    "Subject-To",
    "spoke-seller-finance-outreach":"Seller Finance",
    "spoke-hybrid-outreach":        "Hybrid",
    "spoke-fix-flip-outreach":      "Fix & Flip",
    "spoke-jv-wholesale-outreach":  "JV or Wholesale",
    "spoke-buyers-looking-outreach":"Buyers Looking",
    "spoke-regular-outreach":       "Regular",
}
# Reverse map: category → spoke name (Others has no spoke)
CATEGORY_TO_SPOKE = {v: k for k, v in SPOKE_CATEGORY.items()}
# Key spoke actions to surface in inline action detail
_KEY_SPOKE_ACTIONS = {
    "Get_Lead_From_Table",
    "Call_Gemini_Outreach",
    "Parse_Outreach_Args",
    "Apply_Completeness_Gate",
    "Upsert_Outreach_To_Table",
    "Handle_Outreach_Error",
}

TEST_FILES = [
    ROOT / "dev-utils" / "devi_leads_04.json",
    ROOT / "dev-utils" / "devi_leads_05.json",
]
LOG_DIR      = ROOT / "dev-utils" / "run-logs"
POLL_INTERVAL      = 8   # seconds between status polls
HUB_MAX_WAIT       = 600 # 10 min — accounts for multi-batch runs with 10s inter-batch wait
SPOKE_MAX_WAIT     = 120 # 2 min — spokes are fast (single Gemini responseSchema call)
SPOKE_START_WAIT   = 5   # brief pause after hub completes; spokes already fired during hub
SPOKE_FIND_RETRIES = 6   # retries for find_run_after per spoke (6 × 8s = 48s window)
                         # Azure run-history API can lag ~30s after spoke completion


# ── Azure helpers ─────────────────────────────────────────────────────────────

def _cred():
    return ClientSecretCredential(
        tenant_id=AZURE_TENANT_ID,
        client_id=AZURE_CLIENT_ID,
        client_secret=AZURE_CLIENT_SECRET,
    )

def _logic():
    return LogicManagementClient(_cred(), AZURE_SUBSCRIPTION_ID)


def wait_for_hub_idle(client, max_wait: int = HUB_MAX_WAIT):
    """Block until no hub runs are in a Running state, then return."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            running = [
                r for r in client.workflow_runs.list(AZURE_RESOURCE_GROUP, HUB_NAME)
                if r.status == "Running"
            ]
            if not running:
                return
            print(f"  ⏳ Hub has {len(running)} run(s) still Running — waiting {POLL_INTERVAL}s...")
        except Exception as e:
            print(f"  (idle-check error: {e})")
        time.sleep(POLL_INTERVAL)
    print(f"  ⚠ Hub did not go idle within {max_wait}s — proceeding anyway")


def fire_trigger(payload: dict) -> tuple[str, datetime]:
    """POST to hub trigger. Returns (run_id_hint, trigger_utc_time)."""
    t = datetime.now(timezone.utc)
    print(f"  → POST to hub trigger...")
    resp = requests.post(AZURE_LOGIC_APP_TRIGGER_URL, json=payload, timeout=300)
    resp.raise_for_status()
    run_id = resp.headers.get("x-ms-workflow-run-id", "")
    body = resp.json() if resp.content else {}
    print(f"     HTTP {resp.status_code}  body={body}  run_id_header={run_id or '—'}")
    return run_id, t


def find_run_after(client, workflow: str, after: datetime, retries: int = 10) -> object | None:
    """Find the most recent run of `workflow` started at or after `after`."""
    for attempt in range(retries):
        try:
            for run in client.workflow_runs.list(AZURE_RESOURCE_GROUP, workflow):
                start = run.start_time
                if start is None:
                    continue
                if start.replace(tzinfo=timezone.utc) >= after - timedelta(seconds=5):
                    return run
        except Exception as e:
            print(f"     (find_run_after error attempt {attempt+1}: {e})")
        time.sleep(POLL_INTERVAL)
    return None


def poll_until_done(client, workflow: str, run_name: str, max_wait: int) -> str:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            run = client.workflow_runs.get(AZURE_RESOURCE_GROUP, workflow, run_name)
            status = run.status
            print(f"     [{workflow}] status={status}")
            if status in ("Succeeded", "Failed", "Cancelled", "TimedOut", "Aborted"):
                return status
        except Exception as e:
            print(f"     (poll error: {e})")
        time.sleep(POLL_INTERVAL)
    return "Timeout"


def get_filter_count(client, hub_run_name: str) -> int | None:
    """
    Fetch the output of the hub's Filter_Leads action and return how many leads passed.
    Filter_Leads is a Query action whose output body is the filtered array directly.
    Returns None if the output cannot be retrieved (fallback: treat as >0).
    """
    try:
        action = client.workflow_run_actions.get(
            AZURE_RESOURCE_GROUP, HUB_NAME, hub_run_name, "Filter_Leads"
        )
        link = getattr(action, "output_content_link", None)
        uri  = getattr(link, "uri", None) if link else None
        if not uri:
            return None
        resp = requests.get(uri, timeout=15)
        resp.raise_for_status()
        body = resp.json().get("body", [])
        return len(body) if isinstance(body, list) else None
    except Exception as e:
        print(f"  (could not fetch Filter_Leads output: {e})")
        return None


def get_actions(client, workflow: str, run_name: str) -> list[dict]:
    results = []
    try:
        for action in client.workflow_run_actions.list(AZURE_RESOURCE_GROUP, workflow, run_name):
            err = None
            if action.error:
                try:
                    err = action.error.additional_properties
                except Exception:
                    err = str(action.error)
            results.append({
                "name":       action.name,
                "status":     action.status,
                "start_time": str(action.start_time),
                "end_time":   str(action.end_time),
                "error":      err,
            })
    except Exception as e:
        results.append({"name": "ERROR_LISTING_ACTIONS", "error": str(e)})
    return results


def read_table(lead_ids: list[str] | None = None) -> list[dict]:
    if not AZURE_STORAGE_CONNECTION_STRING:
        return []
    svc = TableServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    tbl = svc.get_table_client("leads")
    rows = []
    try:
        for entity in tbl.list_entities():
            rows.append(dict(entity))
    except Exception as e:
        rows.append({"error": str(e)})
    return rows


def dump_log(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  → Log written: {path}")


# ── Action detail helpers ─────────────────────────────────────────────────────

def _action_duration_secs(action: dict) -> float | None:
    """Return duration in seconds, or None on parse failure."""
    try:
        start = datetime.fromisoformat(str(action["start_time"]).replace("Z", "+00:00"))
        end   = datetime.fromisoformat(str(action["end_time"]).replace("Z", "+00:00"))
        return (end - start).total_seconds()
    except Exception:
        return None


def _fmt_dur(secs: float | None) -> str:
    if secs is None:
        return "—"
    return f"{secs:.1f}s"


def _print_spoke_actions(actions: list[dict]):
    """Print condensed status for key spoke actions."""
    for a in actions:
        name = a.get("name", "")
        if name not in _KEY_SPOKE_ACTIONS:
            continue
        status = a.get("status", "?")
        dur    = _fmt_dur(_action_duration_secs(a))
        err    = a.get("error")
        marker = "✓" if status == "Succeeded" else ("✗" if status == "Failed" else "·")
        suffix = ""
        if name == "Handle_Outreach_Error" and status == "Succeeded":
            suffix = "  ⚠ error handler fired"
        line = f"       {marker} {name:<38} {status:<12} {dur}{suffix}"
        print(line)
        if err:
            print(f"           error: {err}")


# ── Stats computation ─────────────────────────────────────────────────────────

def _to_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).lower() == "true"


def compute_stats(table_rows: list[dict]) -> dict:
    """
    Aggregate outreach metrics across all table rows.

    Returns:
      total_rows      — number of lead rows (excludes SDK error entries)
      outreach_generated — rows with a non-empty outreach_message
      outreach_skipped   — rows where outreach_skipped=true AND no error
      outreach_error     — rows where outreach_skipped=true AND errorMessage != "none"
      outreach_pending   — rows with no outreach output yet (spoke not triggered or still running)
      categories      — per-category breakdown: count/complete/incomplete/skipped/error/pending
      missing_fields  — Counter of field names that appeared in missing_fields lists
    """
    stats: dict = {
        "total_rows":          0,
        "outreach_complete":   0,  # outreach generated + is_complete=True
        "outreach_incomplete": 0,  # outreach generated + is_complete=False
        "outreach_skipped":    0,  # skipped (Others / no-spoke categories), no error
        "outreach_error":      0,  # skipped due to spoke error
        "outreach_pending":    0,  # no outreach output yet
        "categories":         defaultdict(lambda: {
            "count": 0, "complete": 0, "incomplete": 0,
            "skipped": 0, "error": 0, "pending": 0,
        }),
        "missing_fields": Counter(),
    }

    for row in table_rows:
        # Skip SDK-level error rows that have no real lead data
        if "error" in row and "category" not in row:
            continue

        cat = row.get("category", "Unknown")
        stats["total_rows"] += 1
        stats["categories"][cat]["count"] += 1

        is_complete  = _to_bool(row.get("is_complete"))
        skipped      = _to_bool(row.get("outreach_skipped"))
        outreach_msg = (row.get("outreach_message") or "").strip()
        error_msg    = (row.get("errorMessage") or "").strip()
        has_error    = skipped and bool(error_msg) and error_msg.lower() != "none"

        if has_error:
            stats["outreach_error"] += 1
            stats["categories"][cat]["error"] += 1
        elif skipped:
            stats["outreach_skipped"] += 1
            stats["categories"][cat]["skipped"] += 1
        elif outreach_msg:
            if is_complete:
                stats["outreach_complete"] += 1
                stats["categories"][cat]["complete"] += 1
            else:
                stats["outreach_incomplete"] += 1
                stats["categories"][cat]["incomplete"] += 1
        else:
            # Spoke not yet triggered or still running
            stats["outreach_pending"] += 1
            stats["categories"][cat]["pending"] += 1

        # Accumulate missing field names
        missing_raw = row.get("missing_fields") or ""
        if isinstance(missing_raw, str) and missing_raw.strip():
            try:
                fields = json.loads(missing_raw)
            except json.JSONDecodeError:
                fields = [f.strip() for f in missing_raw.split(",") if f.strip()]
            for field in fields:
                if field:
                    stats["missing_fields"][str(field)] += 1
        elif isinstance(missing_raw, (list, tuple)):
            for field in missing_raw:
                if field:
                    stats["missing_fields"][str(field)] += 1

    return stats


# ── Main test runner ──────────────────────────────────────────────────────────

def run_file(payload_file: Path) -> dict:
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    log: dict = {
        "file":        str(payload_file),
        "timestamp":   ts,
        "hub":         {},
        "spokes":      {},
        "table_rows":  [],
        "errors":      [],
    }

    print(f"\n{'='*64}")
    print(f"FILE: {payload_file.name}")
    print(f"{'='*64}")

    with open(payload_file) as f:
        payload = json.load(f)

    items = payload.get("items", [])
    log["input_count"] = len(items)
    print(f"  Items in payload: {len(items)}")

    client = _logic()

    # ── 1. Wait for hub to be idle, then fire trigger ─────────────────────────
    print(f"  → Checking hub is idle before firing...")
    wait_for_hub_idle(client)

    try:
        run_id_hint, trigger_time = fire_trigger(payload)
        log["trigger_time"] = trigger_time.isoformat()
    except Exception as e:
        log["errors"].append(f"Trigger POST failed: {e}")
        print(f"  ✗ Trigger failed: {e}")
        dump_log(log, LOG_DIR / f"e2e_{payload_file.stem}_{ts}.json")
        return log

    # ── 2. Resolve hub run name ───────────────────────────────────────────────
    if run_id_hint:
        hub_run_name = run_id_hint
        print(f"  → Hub run ID (from header): {hub_run_name}")
    else:
        print(f"  → Scanning run history for hub run...")
        hub_run = find_run_after(client, HUB_NAME, trigger_time)
        if not hub_run:
            msg = "Hub run did not appear within wait window"
            log["hub"]["error"] = msg
            log["errors"].append(msg)
            print(f"  ✗ {msg}")
            dump_log(log, LOG_DIR / f"e2e_{payload_file.stem}_{ts}.json")
            return log
        hub_run_name = hub_run.name

    log["hub"]["run_name"] = hub_run_name
    print(f"  → Hub run: {hub_run_name}  polling...")

    hub_status  = poll_until_done(client, HUB_NAME, hub_run_name, HUB_MAX_WAIT)
    hub_actions = get_actions(client, HUB_NAME, hub_run_name)
    log["hub"]["status"]  = hub_status
    log["hub"]["actions"] = hub_actions

    # Use hub's actual Azure start time as reference — more reliable than local trigger_time
    # since the trigger HTTP response header (x-ms-workflow-run-id) may be absent.
    try:
        hub_run_obj = client.workflow_runs.get(AZURE_RESOURCE_GROUP, HUB_NAME, hub_run_name)
        hub_start_time = hub_run_obj.start_time
        if hub_start_time.tzinfo is None:
            hub_start_time = hub_start_time.replace(tzinfo=timezone.utc)
        print(f"  → Hub start time (Azure): {hub_start_time.isoformat()}")
    except Exception as e:
        print(f"  (could not fetch hub start time: {e}) — falling back to trigger_time")
        hub_start_time = trigger_time

    if hub_status != "Succeeded":
        failed = [a for a in hub_actions if a.get("status") == "Failed"]
        log["hub"]["failed_actions"] = failed
        log["errors"].append(f"Hub {hub_status}: {[a['name'] for a in failed]}")
        print(f"  ✗ Hub {hub_status}:")
        for a in failed:
            print(f"     - {a['name']}: {a.get('error')}")
    else:
        print(f"  ✓ Hub Succeeded")

    # ── 3. Check filter output to decide whether any spokes ran ─────────────────
    # Filter_Leads is a Query action — its output body is the exact filtered array.
    # Read it directly from the action output link: no guessing, no DB lookup needed.
    filter_count = get_filter_count(client, hub_run_name)
    if filter_count is None:
        print(f"  → Filter_Leads output unavailable — assuming leads passed, will check table")
    else:
        print(f"  → Filter_Leads output: {filter_count} lead(s) passed")

    # ── 4. Read table + find which spokes to poll ─────────────────────────────
    print(f"  → Reading Table Storage...")
    all_rows = read_table()
    log["table_rows"] = all_rows

    # Rows written in this run (stored_at >= hub's actual Azure start time)
    run_rows = []
    for row in all_rows:
        stored = row.get("stored_at") or ""
        try:
            t = datetime.fromisoformat(stored.replace("Z", "+00:00"))
            if t >= hub_start_time - timedelta(seconds=5):
                run_rows.append(row)
        except (ValueError, AttributeError):
            pass

    triggered_spokes = []
    if filter_count == 0:
        print(f"  → 0 leads passed filter — no spokes triggered")
    else:
        # Hub writes category to table before firing spokes — use that to know exactly
        # which spoke names to scan. No scanning untriggered spokes at all.
        seen_cats = {row.get("category") for row in run_rows if row.get("category")}
        triggered_spokes = [
            CATEGORY_TO_SPOKE[cat] for cat in seen_cats if cat in CATEGORY_TO_SPOKE
        ]
        others_count = sum(1 for r in run_rows if r.get("category") == "Others")
        print(f"  → {len(run_rows)} row(s) this run  categories={seen_cats}"
              + (f"  ({others_count} Others — no spoke)" if others_count else ""))
        print(f"  → Spokes to scan: {[SPOKE_CATEGORY[s] for s in triggered_spokes] or 'none (all Others)'}")

    # ── 5. Find + poll only the spokes that actually ran ─────────────────────
    if triggered_spokes:
        print(f"  → Waiting {SPOKE_START_WAIT}s for spoke run history to surface...")
        time.sleep(SPOKE_START_WAIT)
        spoke_window = hub_start_time - timedelta(seconds=5)

        for spoke in triggered_spokes:
            cat = SPOKE_CATEGORY[spoke]
            spoke_run = find_run_after(client, spoke, spoke_window, retries=SPOKE_FIND_RETRIES)
            if not spoke_run:
                print(f"    ⚠ [{cat}] run not found in API within {SPOKE_FIND_RETRIES * POLL_INTERVAL}s")
                log["errors"].append(f"Spoke {spoke} run not found in API")
                continue

            print(f"  → Spoke [{cat}] run={spoke_run.name}  polling...")
            status  = poll_until_done(client, spoke, spoke_run.name, SPOKE_MAX_WAIT)
            actions = get_actions(client, spoke, spoke_run.name)

            gemini_dur = None
            for a in actions:
                if a.get("name") == "Call_Gemini_Outreach":
                    gemini_dur = _action_duration_secs(a)
                    break

            log["spokes"][spoke] = {
                "run_name":    spoke_run.name,
                "status":      status,
                "category":    cat,
                "gemini_secs": gemini_dur,
                "actions":     actions,
            }

            dur_str = f"  Gemini: {_fmt_dur(gemini_dur)}" if gemini_dur is not None else ""
            if status != "Succeeded":
                failed = [a for a in actions if a.get("status") == "Failed"]
                log["spokes"][spoke]["failed_actions"] = failed
                log["errors"].append(f"Spoke {spoke} {status}: {[a['name'] for a in failed]}")
                print(f"    ✗ [{cat}] {status}:{dur_str}")
                for a in failed:
                    print(f"       - {a['name']}: {a.get('error')}")
            else:
                print(f"    ✓ [{cat}] Succeeded{dur_str}")

            _print_spoke_actions(actions)

    print(f"  → {len(all_rows)} total rows in table  ({len(run_rows)} from this run)")

    dump_log(log, LOG_DIR / f"e2e_{payload_file.stem}_{ts}.json")
    return log


# ── Summary printer ───────────────────────────────────────────────────────────

def print_summary(logs: list[dict]):
    print(f"\n{'='*64}")
    print("RESULTS SUMMARY")
    print(f"{'='*64}")

    for log in logs:
        fname      = Path(log["file"]).name
        hub        = log.get("hub", {})
        spokes_map = log.get("spokes", {})
        rows       = log.get("table_rows", [])
        n_in       = log.get("input_count", "?")
        stats      = compute_stats(rows)

        print(f"\n▶ {fname}  ({n_in} leads in)")
        print(f"  Hub   : {hub.get('status', '—')}")

        # ── Spoke run status line ─────────────────────────────────────────────
        if spokes_map:
            print(f"  Spokes:")
            for spoke, sv in spokes_map.items():
                cat     = sv.get("category", spoke)
                status  = sv.get("status", "—")
                g_secs  = sv.get("gemini_secs")
                dur_str = f"  Gemini: {_fmt_dur(g_secs)}" if g_secs is not None else ""
                marker  = "✓" if status == "Succeeded" else "✗"
                # Flag if error handler fired
                error_handler_fired = any(
                    a.get("name") == "Handle_Outreach_Error" and a.get("status") == "Succeeded"
                    for a in sv.get("actions", [])
                )
                warn = "  ⚠ error handler fired" if error_handler_fired else ""
                print(f"    {marker} [{cat:<18}]  {status:<12}{dur_str}{warn}")
        else:
            print(f"  Spokes: none triggered")

        # ── Filter pass rate ──────────────────────────────────────────────────
        n_rows = stats["total_rows"]
        if isinstance(n_in, int) and n_in > 0:
            pass_rate = f"{n_rows}/{n_in} passed filter ({100*n_rows//n_in}%)"
        else:
            pass_rate = f"{n_rows} rows in table"
        print(f"\n  Table rows: {pass_rate}")

        # ── Per-category classification counts ────────────────────────────────
        if stats["categories"]:
            print(f"\n  Classification breakdown:")
            for cat, c in sorted(stats["categories"].items(), key=lambda x: -x[1]["count"]):
                print(f"    {cat:<22} {c['count']:>2} rows")

        # ── Outreach results ──────────────────────────────────────────────────
        print(f"\n  Outreach results  (of {n_rows} rows):")
        print(f"    Generated — complete   : {stats['outreach_complete']}")
        print(f"    Generated — incomplete : {stats['outreach_incomplete']}")
        print(f"    Skipped (Others/etc.)  : {stats['outreach_skipped']}")
        print(f"    Error                  : {stats['outreach_error']}")
        print(f"    Pending (no output yet): {stats['outreach_pending']}")

        # ── Per-category outreach completeness ────────────────────────────────
        actionable = {
            cat: c for cat, c in stats["categories"].items()
            if c["complete"] + c["incomplete"] > 0
        }
        if actionable:
            print(f"\n  Completeness by category:")
            for cat, c in sorted(actionable.items(), key=lambda x: -x[1]["count"]):
                total_out = c["complete"] + c["incomplete"]
                pct = f"{100*c['complete']//total_out}%" if total_out else "—"
                print(f"    {cat:<22}  {c['complete']}/{total_out} complete ({pct})"
                      f"  incomplete: {c['incomplete']}")

        # ── Top missing fields ────────────────────────────────────────────────
        if stats["missing_fields"]:
            print(f"\n  Top missing fields (across incomplete leads):")
            for field, cnt in stats["missing_fields"].most_common(8):
                print(f"    {field:<25} ×{cnt}")

        # ── Per-row detail ────────────────────────────────────────────────────
        if rows:
            print(f"\n  Per-lead detail:")
            for row in rows:
                if "error" in row and "category" not in row:
                    print(f"    ERROR: {row['error']}")
                    continue
                cat      = row.get("category", "?")
                lid      = (row.get("lead_id") or row.get("RowKey") or "?")[:48]
                msg      = (row.get("outreach_message") or "").strip()[:100]
                missing  = row.get("missing_fields", "") or ""
                complete = _to_bool(row.get("is_complete"))
                skipped  = _to_bool(row.get("outreach_skipped"))
                err_msg  = (row.get("errorMessage") or "").strip()

                badge = "[SKIP]" if skipped else ("[OK]" if complete else "[?] ")
                print(f"    {badge} [{cat}]  {lid}")
                if missing and not skipped:
                    print(f"         missing : {missing}")
                if msg:
                    print(f"         outreach: {msg}{'...' if len(msg)==100 else ''}")
                if err_msg and err_msg.lower() != "none":
                    print(f"         error   : {err_msg}")

        # ── Errors ────────────────────────────────────────────────────────────
        if log.get("errors"):
            print(f"\n  Run errors:")
            for e in log["errors"]:
                print(f"    ✗ {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    files = [Path(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else TEST_FILES
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    all_logs = []
    for f in files:
        result = run_file(f)
        all_logs.append(result)

    print_summary(all_logs)
