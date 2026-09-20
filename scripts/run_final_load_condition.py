#!/usr/bin/env python3
import os
import subprocess
import sys

LOADS = {
    "C-R5": (5, 84000),
    "C-R20": (20, 84100),
    "C-R50": (50, 84200),
}

condition_id = os.environ.get("CONDITION_ID") or (sys.argv[1] if len(sys.argv) > 1 else None)
if condition_id not in LOADS:
    raise SystemExit(f"CONDITION_ID must be one of: {', '.join(LOADS)}")

rate, seed_base = LOADS[condition_id]

for repetition in range(1, 6):
    seed = seed_base + repetition
    env = os.environ.copy()
    env.update({
        "CONDITION_ID": condition_id,
        "RATE": str(rate),
        "MEASUREMENT_DURATION": "60s",
        "WARMUP_DURATION": "15s",
        "SEED": str(seed),
        "REPETITION": str(repetition),
        "PRE_VUS": "100",
        "MAX_VUS": "500",
        "GRACEFUL_STOP": "30s",
        "STRATEGY_LABELS": "S1,S2,S3B3",
        "PROTOCOL_VERSION": "v1.1.1",
        "RUN_MODE": "paper-grade",
        "RESULTS_DIR": f"results/final/load/{condition_id}",
    })
    print(f"\n{condition_id} repetition={repetition} seed={seed}", flush=True)
    subprocess.run(["python3", "scripts/load_cell_runner.py"], check=True, env=env)

print(f"\nfinal load condition {condition_id}: COMPLETE")
