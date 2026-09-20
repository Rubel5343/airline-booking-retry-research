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
protocol_version = os.environ.get("PROTOCOL_VERSION", "v1.1-draft")
run_mode = os.environ.get("RUN_MODE", "validation")
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
    "protocol": protocol_version,
    "runMode": run_mode,
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
            "protocol": protocol_version,
            "runMode": run_mode,
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

    reconciliation_sql = f"""
SELECT COUNT(*)
FROM (
  SELECT logical_booking_id
  FROM simulator.supplier_orders
  WHERE experiment_run_id = '{run_id}'::uuid
  GROUP BY logical_booking_id
  HAVING COUNT(DISTINCT supplier_order_id) > 1
) d;
"""
    raw2 = subprocess.check_output([
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", "research", "-d", "airline_research", "-Atc", reconciliation_sql
    ], text=True).strip()
    reconciled_duplicates = int(raw2 or "0")

    if sql_duplicates != reconciled_duplicates:
        raise SystemExit(
            f"{condition}/{label}: ground-truth reconciliation mismatch "
            f"canonical={sql_duplicates} independent={reconciled_duplicates}"
        )

    duplicate_rate_pct = 100.0 * sql_duplicates / total_requests if total_requests else 0.0

    secondary_sql = f"""
WITH first_create_success AS (
  SELECT DISTINCT logical_booking_id
  FROM simulator.supplier_orders
  WHERE experiment_run_id = '{run_id}'::uuid
    AND create_attempt_no = 1
),
supplier_counts AS (
  SELECT logical_booking_id, COUNT(DISTINCT supplier_order_id) AS supplier_order_count
  FROM simulator.supplier_orders
  WHERE experiment_run_id = '{run_id}'::uuid
  GROUP BY logical_booking_id
),
initial_ambiguous AS (
  SELECT DISTINCT logical_booking_id
  FROM research.booking_events
  WHERE experiment_run_id = '{run_id}'::uuid
    AND event_type = 'ORDER_CREATE_AMBIGUOUS'
    AND COALESCE((metadata->>'createCall')::int, 0) = 1
),
retrieve_unknown AS (
  SELECT attempt_id, MIN(occurred_at) AS first_unknown_at
  FROM research.booking_events
  WHERE experiment_run_id = '{run_id}'::uuid
    AND event_type = 'RETRIEVE_UNKNOWN'
  GROUP BY attempt_id
),
unsafe_after_unknown AS (
  SELECT DISTINCT u.attempt_id
  FROM retrieve_unknown u
  JOIN research.booking_events e
    ON e.attempt_id = u.attempt_id
   AND e.occurred_at > u.first_unknown_at
  WHERE e.event_type = 'CONTROLLED_RETRY_AFTER_NOT_FOUND'
     OR (
       e.event_type = 'ORDER_CREATE_SENT'
       AND COALESCE((e.metadata->>'createCall')::int, 0) >= 2
     )
)
SELECT
  COUNT(*) FILTER (WHERE a.create_call_count >= 2) AS retries,
  COUNT(*) FILTER (
    WHERE a.create_call_count >= 2
      AND f.logical_booking_id IS NOT NULL
  ) AS premature_retries,
  COUNT(*) FILTER (WHERE ia.logical_booking_id IS NOT NULL) AS initial_ambiguous,
  COUNT(*) FILTER (
    WHERE ia.logical_booking_id IS NOT NULL
      AND a.state = 'SUCCESS'
      AND COALESCE(sc.supplier_order_count, 0) = 1
  ) AS recovered_without_duplicate,
  (SELECT COUNT(*) FROM unsafe_after_unknown) AS safety_violations
FROM research.booking_attempts a
LEFT JOIN first_create_success f USING (logical_booking_id)
LEFT JOIN initial_ambiguous ia USING (logical_booking_id)
LEFT JOIN supplier_counts sc USING (logical_booking_id)
WHERE a.experiment_run_id = '{run_id}'::uuid
  AND a.state <> 'SYSTEM_ERROR';
"""
    secondary_raw = subprocess.check_output([
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", "research", "-d", "airline_research",
        "-At", "-F", ",", "-c", secondary_sql
    ], text=True).strip()
    retry_count, premature_count, ambiguous_count, recovered_count, safety_violations = [
        int(x or "0") for x in secondary_raw.split(",")
    ]
    premature_rate_pct = (
        100.0 * premature_count / retry_count if retry_count else 0.0
    )
    recovery_success_pct = (
        100.0 * recovered_count / ambiguous_count if ambiguous_count else 0.0
    )

    output = {
        "runId": run_id,
        "conditionId": condition,
        "label": label,
        "faultCohort": fault_cohort,
        "clientSummary": summary,
        "groundTruth": {
            "duplicateLogicalBookings": sql_duplicates,
            "duplicateRatePct": duplicate_rate_pct,
            "reconciledDuplicateLogicalBookings": reconciled_duplicates,
            "retryingLogicalBookings": retry_count,
            "prematureUnsafeRetries": premature_count,
            "prematureUnsafeRetryRatePct": premature_rate_pct,
            "initialAmbiguousBookings": ambiguous_count,
            "recoveredWithoutDuplicate": recovered_count,
            "recoverySuccessPct": recovery_success_pct,
            "safetyViolationsAfterInconclusiveRetrieve": safety_violations
        },
    }
    evidence_dir = results_dir / "raw" / f"{condition}-r{repetition}-{label}-{run_id}"
    subprocess.run([
        "python3", "scripts/export_run_evidence.py",
        "--run-id", run_id,
        "--output-dir", str(evidence_dir),
        "--protocol", protocol_version,
        "--git-commit", git_commit,
        "--condition-id", condition,
        "--strategy-label", label,
        "--repetition", str(repetition),
    ], check=True, stdout=subprocess.DEVNULL)

    output["evidenceDir"] = str(evidence_dir)
    out_path = results_dir / f"{condition}-r{repetition}-{label}-{run_id}.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    manifest["strategies"].append({
        "label": label,
        "strategy": strategy,
        "retrieveAttempts": retrieve_attempts,
        "runId": run_id,
        "resultFile": str(out_path),
        "evidenceDir": str(evidence_dir),
    })
    print(
        f"{condition} {label}: N={summary['logicalBookings']} "
        f"duplicates={sql_duplicates} premature={premature_count}/{retry_count} "
        f"unknown={summary['unresolvedBookings']} safetyViolations={safety_violations}"
    )

manifest_path = results_dir / f"{condition}-r{repetition}-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"manifest={manifest_path}")
