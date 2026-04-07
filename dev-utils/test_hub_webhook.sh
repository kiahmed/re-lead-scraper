#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# test_hub_webhook.sh
# Fires the hub Logic App trigger URL with a test lead payload via curl.
#
# The trigger URL already contains the SAS token (sig= query param) — no
# separate Bearer header is needed. The URL itself is the credential.
#
# Usage:
#   ./dev-utils/test_hub_webhook.sh                          # uses devi_leads_01.json
#   ./dev-utils/test_hub_webhook.sh dev-utils/devi_leads_04.json
#   ./dev-utils/test_hub_webhook.sh dev-utils/devi_leads_04.json dev-utils/devi_leads_05.json
#
# Run from the project root.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT/.env"

# ── Load .env ────────────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env not found at $ENV_FILE"
  exit 1
fi

# Export only AZURE_LOGIC_APP_TRIGGER_URL from .env (ignore blank/comment lines)
while IFS='=' read -r key value; do
  [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
  key="${key// /}"
  if [[ "$key" == "AZURE_LOGIC_APP_TRIGGER_URL" ]]; then
    export AZURE_LOGIC_APP_TRIGGER_URL="${value}"
  fi
done < "$ENV_FILE"

if [[ -z "${AZURE_LOGIC_APP_TRIGGER_URL:-}" ]]; then
  echo "ERROR: AZURE_LOGIC_APP_TRIGGER_URL is not set in .env"
  exit 1
fi

# ── Resolve payload files ────────────────────────────────────────────────────
if [[ $# -gt 0 ]]; then
  FILES=("$@")
else
  FILES=("$ROOT/dev-utils/mock_unknown_leads.json")
fi

# ── Fire each file ────────────────────────────────────────────────────────────
for PAYLOAD_FILE in "${FILES[@]}"; do
  if [[ ! -f "$PAYLOAD_FILE" ]]; then
    echo "ERROR: payload file not found: $PAYLOAD_FILE"
    continue
  fi

  LEAD_COUNT=$(python3 -c "import json,sys; d=json.load(open('$PAYLOAD_FILE')); print(len(d.get('items',[])))" 2>/dev/null || echo "?")

  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo "  FILE   : $PAYLOAD_FILE"
  echo "  LEADS  : $LEAD_COUNT item(s) in payload"
  echo "  TIME   : $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "════════════════════════════════════════════════════════════════"

  HTTP_RESPONSE=$(curl --silent --write-out "\n---HTTP_STATUS:%{http_code}" \
    --request POST \
    --url "$AZURE_LOGIC_APP_TRIGGER_URL" \
    --header "Content-Type: application/json" \
    --data "@$PAYLOAD_FILE")

  HTTP_BODY=$(echo "$HTTP_RESPONSE" | sed '/---HTTP_STATUS:/d')
  HTTP_STATUS=$(echo "$HTTP_RESPONSE" | grep "^---HTTP_STATUS:" | cut -d: -f2)

  echo "  STATUS : HTTP $HTTP_STATUS"
  echo "  BODY   :"

  # Pretty-print if jq is available, otherwise raw
  if command -v jq &>/dev/null; then
    echo "$HTTP_BODY" | jq . 2>/dev/null || echo "$HTTP_BODY"
  else
    echo "$HTTP_BODY"
  fi

  if [[ "$HTTP_STATUS" == "202" ]]; then
    echo ""
    echo "  ✓ Hub accepted the payload (202) — processing async in Azure"
  else
    echo ""
    echo "  ✗ Unexpected status: $HTTP_STATUS"
  fi
done

echo ""
