"""
Usage:
  python main.py dev-utils/devi_leads_01.json          # from file
  cat dev-utils/devi_leads_01.json | python main.py    # from stdin

Set RUN_MODE=local (default) or RUN_MODE=azure in .env or environment.
"""
import json
import sys
from src.workflows.lead_pipeline import run


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            payload = json.load(f)
    else:
        payload = json.load(sys.stdin)

    results = run(payload)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
