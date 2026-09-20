#!/usr/bin/env bash
set -euo pipefail

SUPPLIER=${SUPPLIER:-http://localhost:8081}
BOOKING=${BOOKING:-http://localhost:8080}

curl -fsS -X PUT "$SUPPLIER/admin/config" \
  -H 'Content-Type: application/json' \
  --data-binary @- >/dev/null <<'JSON'
{
  "randomSeed": 77777,
  "processingDelayMs": 100,
  "processingJitterMs": 0,
  "responseLossProbability": 1.0,
  "definiteFailureProbability": 0.0,
  "transientFailureProbability": 0.0,
  "hiddenSuccessProbabilityOnResponseLoss": 1.0,
  "visibilityDelayMs": 0,
  "retrieveFailureProbability": 1.0,
  "retrieveDelayMs": 10,
  "responseLossHoldMs": 15000
}
JSON

run_id=$(python3 - <<'PY' \
  | curl -fsS -X POST "$BOOKING/experiment-runs" \
      -H 'Content-Type: application/json' \
      --data-binary @- \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["runId"])'
import json
print(json.dumps({"name":"retrieve-failure-safety","randomSeed":77777}))
PY
)

response=$(python3 - "$run_id" <<'PY' \
  | curl -fsS -X POST "$BOOKING/bookings" \
      -H 'Content-Type: application/json' \
      --data-binary @-
import json, sys
print(json.dumps({
  "experimentRunId": sys.argv[1],
  "logicalBookingId": "SAFETY-1",
  "clientReference": "SAFETY-REF-1",
  "origin": "DAC",
  "destination": "LHR",
  "strategy": "RetrieveBeforeRetry",
  "faultCohort": "retrieve-failure-safety",
  "bookingTimeoutMs": 50,
  "retrieveAttempts": 3,
  "retrieveDelayMs": 20
}))
PY
)

state=$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["state"])')
creates=$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["createCallCount"])')
retrieves=$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["retrieveCallCount"])')

sleep 0.2
orders=$(curl -fsS "$SUPPLIER/admin/ground-truth/SAFETY-REF-1?experimentRunId=$run_id" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["orderCount"])')

if [[ "$state" != "UNKNOWN" ]]; then
  echo "Expected UNKNOWN after inconclusive retrieves, got $state" >&2
  exit 1
fi
if [[ "$creates" != "1" ]]; then
  echo "Unsafe retry detected: createCallCount=$creates" >&2
  exit 1
fi
if [[ "$retrieves" != "3" ]]; then
  echo "Expected 3 retrieve attempts, got $retrieves" >&2
  exit 1
fi
if [[ "$orders" != "1" ]]; then
  echo "Expected exactly one supplier order, got $orders" >&2
  exit 1
fi

echo "retrieve-failure-safety: PASS (state=$state creates=$creates retrieves=$retrieves orders=$orders)"
