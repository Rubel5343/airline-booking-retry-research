#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import time
import urllib.request

SUPPLIER = os.environ.get("SUPPLIER", "http://localhost:8081")
BOOKING = os.environ.get("BOOKING", "http://localhost:8080")

condition = os.environ["CONDITION_ID"]
processing_ms = int(os.environ["PROCESSING_MS"])
response_loss = float(os.environ.get("RESPONSE_LOSS", "0"))
visibility_ms = int(os.environ.get("VISIBILITY_MS", "0"))
retrieve_failure = float(os.environ.get("RETRIEVE_FAILURE", "0"))
retrieve_backoff_ms = int(os.environ.get("RETRIEVE_BACKOFF_MS", "250"))
retrieve_endpoint_ms = int(os.environ.get("RETRIEVE_ENDPOINT_MS", "50"))
response_hold_ms = int(os.environ.get("RESPONSE_HOLD_MS", "1500"))
booking_timeout_ms = int(os.environ.get("BOOKING_TIMEOUT_MS", "300"))
delayed_retry_ms = int(os.environ.get("DELAYED_RETRY_MS", "250"))
total_requests = int(os.environ.get("TOTAL_REQUESTS", "8"))
vus = int(os.environ.get("VUS", "8"))
seed = int(os.environ.get("SEED", "71000"))
repetition = int(os.environ.get("REPETITION", "1"))
git_commit = os.environ.get("GIT_COMMIT", os.environ.get("GITHUB_SHA", "unknown"))
strategy_labels = [x.strip() for x in os.environ["STRATEGY_LABELS"].split(",") if x.strip()]

strategy_map = {
    "S1": ("ImmediateBlindRetry", 1),
    "S2": ("DelayedBlindRetry", 1),
    "S3A": ("RetrieveBeforeRetry", 1),
    "S3B3": ("RetrieveBeforeRetry", 3),
    "S3B5": ("RetrieveBeforeRetry", 5),
}

unknown = [x for x in strategy_labels if x not in strategy_map]
if unknown:
    raise SystemExit(f"Unknown strategy labels: {unknown}")

fault_cohort = f"{condition}-rep-{repetition}-seed-{seed}"
results_dir = pathlib.Path(os.environ.get("RESULTS_DIR", "results/v11-validation"))
results_dir.mkdir(parents=True, exist_ok=True)

def request_json(method, url, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}

config = {
    "randomSeed": seed,
    "processingDelayMs": processing_ms,
    "processingJitterMs": 0,
    "responseLossProbability": response_loss,
    "definiteFailureProbability": 0.0,
    "transientFailureProbability": 0.0,
    "hiddenSuccessProbabilityOnResponseLoss": 1.0,
    "visibilityDelayMs": visibility_ms,
    "retrieveFailureProbability": retrieve_failure,
    "retrieveDelayMs": retrieve_endpoint_ms,
    "responseLossHoldMs": response_hold_ms,
}
request_json("PUT", f"{SUPPLIER}/admin/config", config)

manifest = {
    "protocol": "v1.1-draft-validation",
    "conditionId": condition,
    "repetition": repetition,
    "seed": seed,
    "faultCohort": fault_cohort,
    "gitCommit": git_commit,
    "simulatorConfig": config,
    "workload": {
        "bookingTimeoutMs": booking_timeout_ms,
        "delayedRetryMs": delayed_retry_ms,
        "retrieveBackoffMs": retrieve_backoff_ms,
        "totalRequests": total_requests,
        "vus": vus,
    },
    "strategies": [],
}

for label in strategy_labels:
    strategy, retrieve_attempts = strategy_map[label]

    run_payload = {
        "name": f"{condition}-r{repetition}-{label}",
        "randomSeed": seed,
        "gitCommit": git_commit,
        "config": {
            "protocol": "v1.1-draft-validation",
            "conditionId": condition,
            "repetition": repetition,
            "seed": seed,
            "faultCohort": fault_cohort,
            "label": label,
            "strategy": strategy,
            "retrieveAttempts": retrieve_attempts,
            "simulator": config,
        },
    }
    run_id = request_json("POST", f"{BOOKING}/experiment-runs", run_payload)["runId"]

    cmd = [
        "docker", "compose", "--profile", "tools", "run", "--rm",
        "-e", "BOOKING_URL=http://booking-strategy:8080",
        "-e", f"RUN_ID={run_id}",
        "-e", f"STRATEGY={strategy}",
        "-e", f"FAULT_COHORT={fault_cohort}",
        "-e", f"TOTAL_REQUESTS={total_requests}",
        "-e", f"VUS={vus}",
        "-e", f"BOOKING_TIMEOUT_MS={booking_timeout_ms}",
        "-e", f"DELAYED_RETRY_MS={delayed_retry_ms}",
        "-e", f"RETRIEVE_ATTEMPTS={retrieve_attempts}",
        "-e", f"RETRIEVE_DELAY_MS={retrieve_backoff_ms}",
        "k6", "run", "/scripts/booking-fixed.js",
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

    time.sleep(0.6)

    request_json("POST", f"{BOOKING}/experiment-runs/{run_id}/complete")
    summary_payload = request_json("GET", f"{BOOKING}/experiment-runs/{run_id}/summary")
    summaries = summary_payload.get("summary", [])
    if len(summaries) != 1:
        raise SystemExit(f"{condition}/{label}: expected one summary row, got {len(summaries)}")
    summary = summaries[0]

    if int(summary["logicalBookings"]) != total_requests:
        raise SystemExit(
            f"{condition}/{label}: logicalBookings={summary['logicalBookings']} expected={total_requests}"
        )

    sql = f"""
WITH gt AS (
  SELECT logical_booking_id, COUNT(*) AS c
  FROM simulator.supplier_orders
  WHERE experiment_run_id = '{run_id}'::uuid
  GROUP BY logical_booking_id
)
SELECT COUNT(*) FILTER (WHERE c > 1)
FROM gt;
"""
    raw = subprocess.check_output([
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", "research", "-d", "airline_research", "-Atc", sql
    ], text=True).strip()
    sql_duplicates = int(raw or "0")
    api_duplicates = int(summary["duplicateLogicalBookings"])
    if sql_duplicates != api_duplicates:
        raise SystemExit(
            f"{condition}/{label}: API duplicates={api_duplicates} SQL duplicates={sql_duplicates}"
        )

    output = {
        "runId": run_id,
        "conditionId": condition,
        "label": label,
        "faultCohort": fault_cohort,
        "summary": summary,
        "sqlDuplicateLogicalBookings": sql_duplicates,
    }
    out_path = results_dir / f"{condition}-r{repetition}-{label}-{run_id}.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    manifest["strategies"].append({
        "label": label,
        "strategy": strategy,
        "retrieveAttempts": retrieve_attempts,
        "runId": run_id,
        "resultFile": str(out_path),
    })
    print(
        f"{condition} {label}: N={summary['logicalBookings']} "
        f"duplicates={api_duplicates} unknown={summary['unresolvedBookings']}"
    )

manifest_path = results_dir / f"{condition}-r{repetition}-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"manifest={manifest_path}")
