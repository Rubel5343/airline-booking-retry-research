#!/usr/bin/env python3
import os
import random
import subprocess
import sys

CONDITIONS = {
    "A1": dict(processing=200, loss=0.05, visibility=0, retrieve_failure=0.0,
               retrieve_backoff=250, strategies=["S1","S2","S3A","S3B3"], seed_base=81000),
    "A2": dict(processing=200, loss=0.20, visibility=0, retrieve_failure=0.0,
               retrieve_backoff=250, strategies=["S1","S2","S3A","S3B3"], seed_base=81100),
    "A3": dict(processing=330, loss=0.0, visibility=0, retrieve_failure=0.0,
               retrieve_backoff=250, strategies=["S1","S2","S3A","S3B3"], seed_base=81200),
    "A4": dict(processing=500, loss=0.0, visibility=0, retrieve_failure=0.0,
               retrieve_backoff=250, strategies=["S1","S2","S3A","S3B3"], seed_base=81300),
    "B-V0": dict(processing=200, loss=0.20, visibility=0, retrieve_failure=0.0,
                 retrieve_backoff=150, strategies=["S3A","S3B3","S3B5"], seed_base=82000),
    "B-V1": dict(processing=200, loss=0.20, visibility=300, retrieve_failure=0.0,
                 retrieve_backoff=150, strategies=["S3A","S3B3","S3B5"], seed_base=82100),
    "B-V2": dict(processing=200, loss=0.20, visibility=600, retrieve_failure=0.0,
                 retrieve_backoff=150, strategies=["S3A","S3B3","S3B5"], seed_base=82200),
    "B-V4": dict(processing=200, loss=0.20, visibility=1200, retrieve_failure=0.0,
                 retrieve_backoff=150, strategies=["S3A","S3B3","S3B5"], seed_base=82300),
    "D-F0": dict(processing=200, loss=0.20, visibility=300, retrieve_failure=0.0,
                 retrieve_backoff=150, strategies=["S3B3","S3B5"], seed_base=83000),
    "D-F5": dict(processing=200, loss=0.20, visibility=300, retrieve_failure=0.05,
                 retrieve_backoff=150, strategies=["S3B3","S3B5"], seed_base=83100),
    "D-F10": dict(processing=200, loss=0.20, visibility=300, retrieve_failure=0.10,
                  retrieve_backoff=150, strategies=["S3B3","S3B5"], seed_base=83200),
    "D-F20": dict(processing=200, loss=0.20, visibility=300, retrieve_failure=0.20,
                  retrieve_backoff=150, strategies=["S3B3","S3B5"], seed_base=83300),
}

condition_id = os.environ.get("CONDITION_ID") or (sys.argv[1] if len(sys.argv) > 1 else None)
if condition_id not in CONDITIONS:
    raise SystemExit(f"CONDITION_ID must be one of: {', '.join(CONDITIONS)}")

cfg = CONDITIONS[condition_id]
for repetition in range(1, 11):
    seed = cfg["seed_base"] + repetition
    order = list(cfg["strategies"])
    random.Random(seed).shuffle(order)

    env = os.environ.copy()
    env.update({
        "CONDITION_ID": condition_id,
        "PROCESSING_MS": str(cfg["processing"]),
        "RESPONSE_LOSS": str(cfg["loss"]),
        "VISIBILITY_MS": str(cfg["visibility"]),
        "RETRIEVE_FAILURE": str(cfg["retrieve_failure"]),
        "RETRIEVE_BACKOFF_MS": str(cfg["retrieve_backoff"]),
        "STRATEGY_LABELS": ",".join(order),
        "SEED": str(seed),
        "REPETITION": str(repetition),
        "TOTAL_REQUESTS": "500",
        "VUS": "20",
        "BOOKING_TIMEOUT_MS": "300",
        "DELAYED_RETRY_MS": "250",
        "RETRIEVE_ENDPOINT_MS": "50",
        "RESPONSE_HOLD_MS": "1500",
        "PROTOCOL_VERSION": "v1.1",
        "RUN_MODE": "paper-grade",
        "RESULTS_DIR": f"results/final/correctness/{condition_id}",
    })
    print(
        f"\n{condition_id} repetition={repetition} seed={seed} "
        f"order={' '.join(order)}", flush=True
    )
    subprocess.run(["python3", "scripts/fixed_cell_runner.py"], check=True, env=env)

print(f"\nfinal correctness condition {condition_id}: COMPLETE")
