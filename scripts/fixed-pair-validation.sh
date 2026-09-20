#!/usr/bin/env bash
set -euo pipefail

SUPPLIER=${SUPPLIER:-http://localhost:8081}
BOOKING=${BOOKING:-http://localhost:8080}
TOTAL_REQUESTS=${TOTAL_REQUESTS:-20}
VUS=${VUS:-10}
SEED=${SEED:-61000}
FAULT_COHORT=${FAULT_COHORT:-fixed-pair-validation}
SCENARIO=${SCENARIO:-configs/scenario-baseline.json}

create_run() {
  local name=$1
  local strategy=$2
  python3 - "$name" "$strategy" "$SEED" "$FAULT_COHORT" "$TOTAL_REQUESTS" <<'PY' \
    | curl -fsS -X POST "$BOOKING/experiment-runs" \
        -H 'Content-Type: application/json' \
        --data-binary @- \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["runId"])'
import json, sys
print(json.dumps({
    "name": sys.argv[1],
    "randomSeed": int(sys.argv[3]),
    "config": {
        "strategy": sys.argv[2],
        "faultCohort": sys.argv[4],
        "totalRequests": int(sys.argv[5]),
        "validation": "fixed-pair"
    }
}))
PY
}

apply_config() {
  python3 - "$SCENARIO" "$SEED" <<'PY' \
    | curl -fsS -X PUT "$SUPPLIER/admin/config" \
        -H 'Content-Type: application/json' \
        --data-binary @- >/dev/null
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    cfg = json.load(f)
cfg["randomSeed"] = int(sys.argv[2])
print(json.dumps(cfg))
PY
}

run_fixed() {
  local run_id=$1
  local strategy=$2
  local retrieves=$3
  docker compose --profile tools run --rm \
    -e BOOKING_URL=http://booking-strategy:8080 \
    -e RUN_ID="$run_id" \
    -e STRATEGY="$strategy" \
    -e FAULT_COHORT="$FAULT_COHORT" \
    -e TOTAL_REQUESTS="$TOTAL_REQUESTS" \
    -e VUS="$VUS" \
    -e BOOKING_TIMEOUT_MS=300 \
    -e DELAYED_RETRY_MS=250 \
    -e RETRIEVE_ATTEMPTS="$retrieves" \
    -e RETRIEVE_DELAY_MS=250 \
    k6 run /scripts/booking-fixed.js >/dev/null
}

apply_config

run_s1=$(create_run "fixed-pair-s1" "ImmediateBlindRetry")
run_s3=$(create_run "fixed-pair-s3b" "RetrieveBeforeRetry")

run_fixed "$run_s1" "ImmediateBlindRetry" 1
run_fixed "$run_s3" "RetrieveBeforeRetry" 3

count_s1=$(curl -fsS "$BOOKING/experiment-runs/$run_s1/summary" | python3 -c 'import json,sys; print(json.load(sys.stdin)["summary"][0]["logicalBookings"])')
count_s3=$(curl -fsS "$BOOKING/experiment-runs/$run_s3/summary" | python3 -c 'import json,sys; print(json.load(sys.stdin)["summary"][0]["logicalBookings"])')

if [[ "$count_s1" != "$TOTAL_REQUESTS" || "$count_s3" != "$TOTAL_REQUESTS" ]]; then
  echo "Fixed-count mismatch: S1=$count_s1 S3B=$count_s3 expected=$TOTAL_REQUESTS" >&2
  exit 1
fi

mismatches=$(docker compose exec -T postgres psql -U research -d airline_research -Atc "
WITH a AS (
  SELECT client_reference, outcome
  FROM simulator.supplier_calls
  WHERE experiment_run_id = '$run_s1'::uuid
    AND operation = 'CREATE'
    AND operation_attempt_no = 1
),
b AS (
  SELECT client_reference, outcome
  FROM simulator.supplier_calls
  WHERE experiment_run_id = '$run_s3'::uuid
    AND operation = 'CREATE'
    AND operation_attempt_no = 1
)
SELECT COUNT(*)
FROM a FULL OUTER JOIN b USING (client_reference)
WHERE a.client_reference IS NULL
   OR b.client_reference IS NULL
   OR a.outcome IS DISTINCT FROM b.outcome;
")

if [[ "$mismatches" != "0" ]]; then
  echo "Fault pairing mismatch count=$mismatches" >&2
  exit 1
fi

echo "fixed-pair-validation: PASS (N=$TOTAL_REQUESTS, first-create mismatches=0)"
