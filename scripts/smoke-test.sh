#!/usr/bin/env bash
set -euo pipefail

SUPPLIER=${SUPPLIER:-http://localhost:8081}
BOOKING=${BOOKING:-http://localhost:8080}

curl -fsS -X PUT "$SUPPLIER/admin/config"   -H 'Content-Type: application/json'   --data-binary @configs/scenario-baseline.json >/dev/null

curl -fsS -X POST "$SUPPLIER/admin/reset" >/dev/null

RUN_ID=$(curl -fsS -X POST "$BOOKING/experiment-runs"   -H 'Content-Type: application/json'   -d '{"name":"smoke","randomSeed":12345}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["runId"])')

echo "runId=$RUN_ID"

curl -fsS -X POST "$BOOKING/bookings"   -H 'Content-Type: application/json'   -d "{"experimentRunId":"$RUN_ID","logicalBookingId":"BKG-1","clientReference":"EXP-1","origin":"DAC","destination":"LHR","strategy":"RetrieveBeforeRetry","bookingTimeoutMs":3000,"delayedRetryMs":1000,"retrieveAttempts":3,"retrieveDelayMs":1000}"

echo
