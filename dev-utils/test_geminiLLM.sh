PAYLOAD=$( cat ./payload4.json)
source ./.env
if [ -z "$GEMINI_API_KEY" ]; then
  echo "ERROR: GEMINI_API_KEY env var not set"
  exit 1
fi

curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent" \
  -H 'Content-Type: application/json' \
  -H "X-goog-api-key: $GEMINI_API_KEY" \
  -X POST \
  -d "$PAYLOAD"

