"""
Smoke test for Gemini classify — runs filter + classify against sample data
and pretty-prints the response.

Run from the project root:
  python3 dev-utils/test_classify.py
  python3 dev-utils/test_classify.py dev-utils/devi_leads_02.json
"""
import json
import sys
import os

# Always resolve paths relative to project root regardless of where script is invoked from
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.config import GEMINI_API_KEY, GEMINI_MODEL
from src.agents.filter_agent import filter_leads
from src.agents.classifier_agent import classify_leads

payload_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dev-utils", "devi_leads_01.json")

with open(payload_file) as f:
    payload = json.load(f)

leads = payload.get("items", [])
filtered = filter_leads(leads)

print(f"File       : {payload_file}")
print(f"Input leads: {len(leads)}")
print(f"After filter: {len(filtered)}")
if not filtered:
    print("No leads passed the filter — nothing to classify.")
    sys.exit(0)

for l in filtered:
    print(f"  -> {l['authorName']} | keywords: {l['keywords']}")

print(f"\nCalling Gemini ({GEMINI_MODEL})...")
results = classify_leads(filtered, GEMINI_API_KEY, GEMINI_MODEL)

print(f"\n--- Results ({len(results)}) ---")
for r in results:
    info = json.loads(r["extracted_info"]) if isinstance(r["extracted_info"], str) else r["extracted_info"]
    print(f"\n[{r['category']}]  source: {r['source_id']}")
    print(f"  contact : {r['contact']}")
    print(f"  info    : {json.dumps(info, indent=10).strip()}")
