#!/usr/bin/env bash
set -euo pipefail

SUPPLIER=${SUPPLIER:-http://localhost:8081}
BOOKING=${BOOKING:-http://localhost:8080}
SCENARIO=${SCENARIO:-configs/scenario-ambiguity-smoke.json}

create_run() {
  local name=$1
  python3 - "$name" <<'PY'     | curl -fsS -X POST "$BOOKING/experiment-runs"         -H 'Content-Type: application/json'         --data-binary @-     | python3 -c 'import json,sys; print(json.load(sys.stdin)["runId"])'
import json, sys
print(json.dumps({"name": sys.argv[1], "randomSeed": 12345}))
PY
}

book() {
  local run_id=$1
  local logical=$2
  local ref=$3
  local strategy=$4
  local retrieves=$5

  python3 - "$run_id" "$logical" "$ref" "$strategy" "$retrieves" <<'PY'     | curl -fsS -X POST "$BOOKING/bookings"         -H 'Content-Type: application/json'         --data-binary @- >/dev/null
import json, sys
print(json.dumps({
    "experimentRunId": sys.argv[1],
    "logicalBookingId": sys.argv[2],
    "clientReference": sys.argv[3],
    "origin": "DAC",
    "destination": "LHR",
    "strategy": sys.argv[4],
    "bookingTimeoutMs": 300,
    "delayedRetryMs": 250,
    "retrieveAttempts": int(sys.argv[5]),
    "retrieveDelayMs": 250
}))
PY
}

order_count() {
  local run_id=$1
  local ref=$2
  curl -fsS "$SUPPLIER/admin/ground-truth/$ref?experimentRunId=$run_id"     | python3 -c 'import json,sys; print(json.load(sys.stdin)["orderCount"])'
}

curl -fsS -X PUT "$SUPPLIER/admin/config"   -H 'Content-Type: application/json'   --data-binary @"$SCENARIO" >/dev/null

blind_run=$(create_run "ambiguity-smoke-blind")
book "$blind_run" "BKG-BLIND" "REF-BLIND" "ImmediateBlindRetry" 1
sleep 1.2
blind_count=$(order_count "$blind_run" "REF-BLIND")
if [[ "$blind_count" != "2" ]]; then
  echo "Expected blind retry to create 2 supplier orders, got $blind_count" >&2
  exit 1
fi

retrieve_run=$(create_run "ambiguity-smoke-retrieve")
book "$retrieve_run" "BKG-RETRIEVE" "REF-RETRIEVE" "RetrieveBeforeRetry" 3
sleep 0.3
retrieve_count=$(order_count "$retrieve_run" "REF-RETRIEVE")
if [[ "$retrieve_count" != "1" ]]; then
  echo "Expected bounded retrieve-before-retry to create 1 supplier order, got $retrieve_count" >&2
  exit 1
fi

echo "ambiguity-smoke: PASS (blind=$blind_count, retrieve-before-retry=$retrieve_count)"
