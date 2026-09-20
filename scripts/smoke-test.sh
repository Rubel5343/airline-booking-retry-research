#!/usr/bin/env bash
set -euo pipefail

SUPPLIER=${SUPPLIER:-http://localhost:8081}
BOOKING=${BOOKING:-http://localhost:8080}

curl -fsS -X PUT "$SUPPLIER/admin/config"   -H 'Content-Type: application/json'   --data-binary @configs/scenario-baseline.json >/dev/null

curl -fsS -X POST "$SUPPLIER/admin/reset" >/dev/null

RUN_PAYLOAD=$(python3 - <<'PY'
import json
print(json.dumps({"name":"smoke","randomSeed":12345}))
PY
)

RUN_ID=$(printf '%s' "$RUN_PAYLOAD" | curl -fsS -X POST "$BOOKING/experiment-runs"   -H 'Content-Type: application/json'   --data-binary @-   | python3 -c 'import sys,json; print(json.load(sys.stdin)["runId"])')

echo "runId=$RUN_ID"

BOOKING_PAYLOAD=$(python3 - "$RUN_ID" <<'PY'
import json, sys
run_id = sys.argv[1]
print(json.dumps({
    "experimentRunId": run_id,
    "logicalBookingId": "BKG-1",
    "clientReference": "EXP-1",
    "origin": "DAC",
    "destination": "LHR",
    "strategy": "RetrieveBeforeRetry",
    "bookingTimeoutMs": 3000,
    "delayedRetryMs": 1000,
    "retrieveAttempts": 3,
    "retrieveDelayMs": 1000
}))
PY
)

printf '%s' "$BOOKING_PAYLOAD" | curl -fsS -X POST "$BOOKING/bookings"   -H 'Content-Type: application/json'   --data-binary @-

echo
