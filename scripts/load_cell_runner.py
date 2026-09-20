#!/usr/bin/env python3
import json
import os
import pathlib
import random
import subprocess
import time
import urllib.request

SUPPLIER = os.environ.get("SUPPLIER", "http://localhost:8081")
BOOKING = os.environ.get("BOOKING", "http://localhost:8080")

condition = os.environ["CONDITION_ID"]
rate = int(os.environ["RATE"])
measurement_duration = os.environ.get("MEASUREMENT_DURATION", "60s")
warmup_duration = os.environ.get("WARMUP_DURATION", "15s")
seed = int(os.environ.get("SEED", "72000"))
repetition = int(os.environ.get("REPETITION", "1"))
protocol_version = os.environ.get("PROTOCOL_VERSION", "v1.1-draft")
run_mode = os.environ.get("RUN_MODE", "validation")
git_commit = os.environ.get("GIT_COMMIT", os.environ.get("GITHUB_SHA", "unknown"))
pre_vus = int(os.environ.get("PRE_VUS", "100"))
max_vus = int(os.environ.get("MAX_VUS", "500"))
graceful_stop = os.environ.get("GRACEFUL_STOP", "30s")
strategy_labels = [x.strip() for x in os.environ.get("STRATEGY_LABELS", "S1,S2,S3B3").split(",") if x.strip()]

strategy_map = {
    "S1": ("ImmediateBlindRetry", 1),
    "S2": ("DelayedBlindRetry", 1),
    "S3B3": ("RetrieveBeforeRetry", 3),
}
if any(x not in strategy_map for x in strategy_labels):
    raise SystemExit(f"Unsupported load strategy labels: {strategy_labels}")

rng = random.Random(seed)
strategy_order = strategy_labels.copy()
rng.shuffle(strategy_order)

results_root = pathlib.Path("results")
results_root.mkdir(parents=True, exist_ok=True)
os.chmod(results_root, 0o777)

results_dir = pathlib.Path(os.environ.get("RESULTS_DIR", "results/v11-load-validation"))
results_dir.mkdir(parents=True, exist_ok=True)
os.chmod(results_dir, 0o777)

try:
    results_dir.relative_to(results_root)
except ValueError as exc:
    raise SystemExit("RESULTS_DIR must be inside the repository results/ directory") from exc

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

simulator_config = {
    "randomSeed": seed,
    "processingDelayMs": 500,
    "processingJitterMs": 0,
    "responseLossProbability": 0.0,
    "definiteFailureProbability": 0.0,
    "transientFailureProbability": 0.0,
    "hiddenSuccessProbabilityOnResponseLoss": 1.0,
    "visibilityDelayMs": 0,
    "retrieveFailureProbability": 0.0,
    "retrieveDelayMs": 50,
    "responseLossHoldMs": 1500,
}
request_json("PUT", f"{SUPPLIER}/admin/config", simulator_config)

def create_run(name, label, strategy, phase, cohort):
    payload = {
        "name": name,
        "randomSeed": seed,
        "gitCommit": git_commit,
        "config": {
            "protocol": protocol_version,
            "runMode": run_mode,
            "conditionId": condition,
            "phase": phase,
            "repetition": repetition,
            "seed": seed,
            "rate": rate,
            "strategyLabel": label,
            "strategy": strategy,
            "faultCohort": cohort,
            "simulator": simulator_config,
        },
    }
    return request_json("POST", f"{BOOKING}/experiment-runs", payload)["runId"]

def run_k6(run_id, label, strategy, retrieves, cohort, duration, summary_path):
    cmd = [
        "docker", "compose", "--profile", "tools", "run", "--rm",
        "-e", "BOOKING_URL=http://booking-strategy:8080",
        "-e", f"RUN_ID={run_id}",
        "-e", f"STRATEGY={strategy}",
        "-e", f"FAULT_COHORT={cohort}",
        "-e", f"RATE={rate}",
        "-e", f"DURATION={duration}",
        "-e", "BOOKING_TIMEOUT_MS=300",
        "-e", "DELAYED_RETRY_MS=250",
        "-e", f"RETRIEVE_ATTEMPTS={retrieves}",
        "-e", "RETRIEVE_DELAY_MS=250",
        "-e", f"PRE_VUS={pre_vus}",
        "-e", f"MAX_VUS={max_vus}",
        "-e", f"GRACEFUL_STOP={graceful_stop}",
        "k6", "run",
        f"--summary-export=/results/{summary_path.relative_to(results_root).as_posix()}",
        "/scripts/booking.js",
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    time.sleep(0.6)

def parse_seconds(value):
    value = value.strip().lower()
    if value.endswith("ms"):
        return float(value[:-2]) / 1000.0
    if value.endswith("s"):
        return float(value[:-1])
    if value.endswith("m"):
        return float(value[:-1]) * 60.0
    raise ValueError(f"Unsupported duration: {value}")

manifest = {
    "protocol": protocol_version,
    "runMode": run_mode,
    "conditionId": condition,
    "rate": rate,
    "seed": seed,
    "repetition": repetition,
    "gitCommit": git_commit,
    "strategyOrder": strategy_order,
    "warmupDuration": warmup_duration,
    "measurementDuration": measurement_duration,
    "preVUs": pre_vus,
    "maxVUs": max_vus,
    "gracefulStop": graceful_stop,
    "runs": [],
}

for label in strategy_order:
    strategy, retrieves = strategy_map[label]

    warmup_cohort = f"{condition}-warmup-r{repetition}-{label}-seed-{seed}"
    warmup_id = create_run(f"{condition}-warmup-r{repetition}-{label}", label, strategy, "warmup", warmup_cohort)
    warmup_summary = results_dir / f"{condition}-r{repetition}-{label}-warmup-k6.json"
    run_k6(warmup_id, label, strategy, retrieves, warmup_cohort, warmup_duration, warmup_summary)
    request_json("POST", f"{BOOKING}/experiment-runs/{warmup_id}/complete")

    cohort = f"{condition}-measurement-r{repetition}-seed-{seed}"
    run_id = create_run(f"{condition}-r{repetition}-{label}", label, strategy, "measurement", cohort)
    k6_path = results_dir / f"{condition}-r{repetition}-{label}-k6.json"
    run_k6(run_id, label, strategy, retrieves, cohort, measurement_duration, k6_path)
    request_json("POST", f"{BOOKING}/experiment-runs/{run_id}/complete")

    client_payload = request_json("GET", f"{BOOKING}/experiment-runs/{run_id}/summary")
    client_summary = client_payload["summary"][0]

    sql = f"""
WITH gt AS (
  SELECT logical_booking_id, COUNT(DISTINCT supplier_order_id) AS c
  FROM simulator.supplier_orders
  WHERE experiment_run_id = '{run_id}'::uuid
  GROUP BY logical_booking_id
)
SELECT COUNT(*) FILTER (WHERE c > 1) FROM gt;
"""
    duplicate_count = int(subprocess.check_output([
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", "research", "-d", "airline_research", "-Atc", sql
    ], text=True).strip() or "0")

    k6_summary = json.loads(k6_path.read_text(encoding="utf-8"))
    metrics = k6_summary.get("metrics", {})
    iterations = int(metrics.get("iterations", {}).get("values", {}).get("count", 0))
    dropped = int(metrics.get("dropped_iterations", {}).get("values", {}).get("count", 0))
    target = rate * parse_seconds(measurement_duration)
    achieved_ratio = iterations / target if target else 0.0

    output = {
        "protocol": protocol_version,
        "runMode": run_mode,
        "conditionId": condition,
        "label": label,
        "strategy": strategy,
        "runId": run_id,
        "rate": rate,
        "targetIterations": target,
        "completedIterations": iterations,
        "droppedIterations": dropped,
        "achievedRequestedRatio": achieved_ratio,
        "clientSummary": client_summary,
        "groundTruth": {
            "duplicateLogicalBookings": duplicate_count,
            "duplicateRatePct": (
                100.0 * duplicate_count / int(client_summary["logicalBookings"])
                if int(client_summary["logicalBookings"]) else 0.0
            ),
        },
        "k6SummaryFile": str(k6_path),
        "warmupRunId": warmup_id,
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
    out_path = results_dir / f"{condition}-r{repetition}-{label}-result.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    manifest["runs"].append(output)
    print(
        f"{condition} {label}: completed={iterations} dropped={dropped} "
        f"ratio={achieved_ratio:.3f} duplicates={duplicate_count}"
    )

manifest_path = results_dir / f"{condition}-r{repetition}-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"manifest={manifest_path}")
