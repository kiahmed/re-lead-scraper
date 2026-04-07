"""
Smoke test for the full pipeline including outreach agents.
Runs filter → classify → outreach against sample data and dumps output.

Run from the project root:
  python3 dev-utils/test_outreach.py
  python3 dev-utils/test_outreach.py dev-utils/devi_leads_01.json
"""
import json
import sys
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_THINKING_LEVEL
from src.agents.filter_agent import filter_leads
from src.agents.classifier_agent import classify_leads
from src.agents.outreach import dispatch_outreach

payload_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dev-utils", "devi_leads_01.json")

with open(payload_file) as f:
    payload = json.load(f)

leads = payload.get("items", [])
filtered = filter_leads(leads)

print(f"File        : {payload_file}")
print(f"Input leads : {len(leads)}")
print(f"After filter: {len(filtered)}")

if not filtered:
    print("No leads passed the filter — nothing to process.")
    sys.exit(0)

print(f"\nClassifying ({GEMINI_MODEL})...")
classified = classify_leads(filtered, GEMINI_API_KEY, GEMINI_MODEL, GEMINI_THINKING_LEVEL)

print(f"\nDispatching outreach for {len(classified)} leads...")
leads_by_id = {lead["id"]: lead for lead in filtered}
outreach_results = dispatch_outreach(classified, leads_by_id, GEMINI_API_KEY, GEMINI_MODEL, GEMINI_THINKING_LEVEL)
outreach_by_id = {r["source_id"]: r["outreach"] for r in outreach_results}

print(f"\n{'='*70}")
print("FULL RESULTS")
print(f"{'='*70}")

merged = []
for c in classified:
    sid = c["source_id"]
    outreach = outreach_by_id.get(sid)
    entry = {**c, "outreach": outreach}
    merged.append(entry)

    info = json.loads(c["extracted_info"]) if isinstance(c["extracted_info"], str) else c["extracted_info"]
    print(f"\n[{c['category']}]  {sid}")
    print(f"  contact  : {c['contact']}")
    print(f"  info     : {json.dumps(info, indent=12).strip()}")

    if outreach:
        print(f"  complete : {outreach['is_complete']}")
        if outreach.get("missing_fields"):
            print(f"  missing  : {outreach['missing_fields']}")
        print(f"  message  :\n    {outreach['outreach_message'].replace(chr(10), chr(10)+'    ')}")
        if outreach.get("investment_summary"):
            print(f"  summary  : {outreach['investment_summary']}")
        if outreach.get("location_insights"):
            print(f"  location : {json.dumps(outreach['location_insights'], indent=12).strip()}")
    else:
        print("  outreach : skipped (Others or error)")

# ── Dump to run-logs ──────────────────────────────────────────────────────────
log_dir = os.path.join(ROOT, "dev-utils", "run-logs")
os.makedirs(log_dir, exist_ok=True)
base_name = os.path.splitext(os.path.basename(payload_file))[0]
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = os.path.join(log_dir, f"outreach_{base_name}_{ts}.json")
with open(log_path, "w") as f:
    json.dump(merged, f, indent=2)
print(f"\nLog written → {log_path}")
