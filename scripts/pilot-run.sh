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
RETRIEVE_ATTEMPTS=${RETRIEVE_ATTEMPTS:-3}
SEED=${SEED:-12345}

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

create_run() {
  local strategy=$1
  curl -fsS -X POST "$BOOKING/experiment-runs"     -H 'Content-Type: application/json'     -d "{"name":"pilot-${strategy}","randomSeed":${SEED},"config":{"scenario":"${SCENARIO}","rate":${RATE},"duration":"${DURATION}"}}"     | python3 -c 'import json,sys; print(json.load(sys.stdin)["runId"])'
}

run_strategy() {
  local strategy=$1
  local retrieve_attempts=$2

  echo
  echo "=== $strategy (retrieveAttempts=$retrieve_attempts) ==="

  curl -fsS -X PUT "$SUPPLIER/admin/config"     -H 'Content-Type: application/json'     --data-binary @"$SCENARIO" >/dev/null

  local run_id
  run_id=$(create_run "$strategy")
  echo "runId=$run_id"

  docker compose --profile tools run --rm     -e BOOKING_URL=http://booking-strategy:8080     -e RUN_ID="$run_id"     -e STRATEGY="$strategy"     -e RATE="$RATE"     -e DURATION="$DURATION"     -e BOOKING_TIMEOUT_MS="$BOOKING_TIMEOUT_MS"     -e DELAYED_RETRY_MS="$DELAYED_RETRY_MS"     -e RETRIEVE_ATTEMPTS="$retrieve_attempts"     -e RETRIEVE_DELAY_MS="$RETRIEVE_DELAY_MS"     k6 run /scripts/booking.js

  curl -fsS -X POST "$BOOKING/experiment-runs/$run_id/complete" >/dev/null
  echo "Summary:"
  curl -fsS "$BOOKING/experiment-runs/$run_id/summary" | python3 -m json.tool
}

wait_for "$SUPPLIER/health"
wait_for "$BOOKING/health"

run_strategy ImmediateBlindRetry 1
run_strategy DelayedBlindRetry 1
run_strategy RetrieveBeforeRetry 1
run_strategy RetrieveBeforeRetry 3
