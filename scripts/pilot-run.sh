#!/usr/bin/env bash
set -euo pipefail

SUPPLIER=${SUPPLIER:-http://localhost:8081}
BOOKING=${BOOKING:-http://localhost:8080}
SCENARIO=${SCENARIO:-configs/scenario-baseline.json}
RATE=${RATE:-5}
DURATION=${DURATION:-30s}
BOOKING_TIMEOUT_MS=${BOOKING_TIMEOUT_MS:-300}
DELAYED_RETRY_MS=${DELAYED_RETRY_MS:-250}
RETRIEVE_DELAY_MS=${RETRIEVE_DELAY_MS:-250}
SEED=${SEED:-12345}
REPETITION=${REPETITION:-1}
ORDER=${ORDER:-"S1 S2 S3A S3B"}
FAULT_COHORT=${FAULT_COHORT:-"pilot-rep-${REPETITION}-seed-${SEED}"}
GIT_COMMIT=${GIT_COMMIT:-${GITHUB_SHA:-unknown}}

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

wait_for() {
  local url=$1
  for _ in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for $url" >&2
  exit 1
}

apply_scenario_config() {
  python3 - "$SCENARIO" "$SEED" <<'PY' \
    | curl -fsS -X PUT "$SUPPLIER/admin/config" \
        -H 'Content-Type: application/json' \
        --data-binary @- >/dev/null
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    config = json.load(handle)
config["randomSeed"] = int(sys.argv[2])
print(json.dumps(config))
PY
}

create_run() {
  local strategy=$1
  local variant=$2

  python3 - "$strategy" "$variant" "$SEED" "$SCENARIO" "$RATE" "$DURATION" \
    "$REPETITION" "$FAULT_COHORT" "$GIT_COMMIT" <<'PY' \
    | curl -fsS -X POST "$BOOKING/experiment-runs" \
        -H 'Content-Type: application/json' \
        --data-binary @- \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["runId"])'
import json, sys
print(json.dumps({
    "name": f"pilot-r{sys.argv[7]}-{sys.argv[2]}",
    "randomSeed": int(sys.argv[3]),
    "gitCommit": sys.argv[9],
    "config": {
        "strategy": sys.argv[1],
        "variant": sys.argv[2],
        "scenario": sys.argv[4],
        "rate": int(sys.argv[5]),
        "duration": sys.argv[6],
        "repetition": int(sys.argv[7]),
        "faultCohort": sys.argv[8]
    }
}))
PY
}

run_strategy() {
  local label=$1
  local strategy=$2
  local retrieve_attempts=$3

  echo
  echo "=== repetition=$REPETITION label=$label strategy=$strategy retrieves=$retrieve_attempts cohort=$FAULT_COHORT ==="

  apply_scenario_config

  local run_id
  run_id=$(create_run "$strategy" "$label")
  echo "runId=$run_id"

  docker compose --profile tools run --rm \
    -e BOOKING_URL=http://booking-strategy:8080 \
    -e RUN_ID="$run_id" \
    -e STRATEGY="$strategy" \
    -e FAULT_COHORT="$FAULT_COHORT" \
    -e RATE="$RATE" \
    -e DURATION="$DURATION" \
    -e BOOKING_TIMEOUT_MS="$BOOKING_TIMEOUT_MS" \
    -e DELAYED_RETRY_MS="$DELAYED_RETRY_MS" \
    -e RETRIEVE_ATTEMPTS="$retrieve_attempts" \
    -e RETRIEVE_DELAY_MS="$RETRIEVE_DELAY_MS" \
    k6 run /scripts/booking.js

  curl -fsS -X POST "$BOOKING/experiment-runs/$run_id/complete" >/dev/null

  mkdir -p results
  local summary_file="results/r${REPETITION}-${label}-${run_id}.json"
  curl -fsS "$BOOKING/experiment-runs/$run_id/summary" \
    | tee "$summary_file" \
    | python3 -m json.tool
  echo "summaryFile=$summary_file"
}

wait_for "$SUPPLIER/health"
wait_for "$BOOKING/health"

for label in $ORDER; do
  case "$label" in
    S1)  run_strategy S1 ImmediateBlindRetry 1 ;;
    S2)  run_strategy S2 DelayedBlindRetry 1 ;;
    S3A) run_strategy S3A RetrieveBeforeRetry 1 ;;
    S3B) run_strategy S3B RetrieveBeforeRetry 3 ;;
    *)
      echo "Unknown strategy label in ORDER: $label" >&2
      exit 2
      ;;
  esac
done
